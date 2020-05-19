import math
import os
import time
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.styling import enable_colors, fg
from easyshare.utils.env import is_unicode_supported, terminal_size
from easyshare.utils.measures import duration_str_human, size_str, speed_str

log = get_logger(__name__)

class ProgressBarStyle(Enum):
    AUTO = object()
    ASCII = object()
    UNICODE = object()


class ProgressBarRenderer(ABC):
    @abstractmethod
    def render(self, inner_width: int, progress_ratio: float) -> Tuple[str, str, str]:
        pass


class ProgressBarRendererAscii(ProgressBarRenderer):

    def __init__(self, mark: str = "="):
        self.mark = mark

    def render(self, inner_width: int, progress_ratio: float) -> Tuple[str, str, str]:
        return (
            "[",
            "{}".format(
                self.mark * int(progress_ratio * inner_width)
            ),
            "]"
        )


class ProgressBarRendererUnicode(ProgressBarRenderer):

    NON_FULL_BLOCKS = [
        "",
        "\u258f",
        "\u258e",
        "\u258d",
        "\u258c",
        "\u258b",
        "\u258a",
        "\u2589"
    ]
    NON_FULL_BLOCKS_COUNT = len(NON_FULL_BLOCKS)
    BLOCK_FULL = "\u2588"
    VBAR = "\u2502"

    def render(self, inner_width: int, progress_ratio: float) -> Tuple[str, str, str]:
        last_block_filling, full_blocks = math.modf(inner_width * progress_ratio)
        last_block_chr = ProgressBarRendererUnicode.NON_FULL_BLOCKS[
            int(last_block_filling * ProgressBarRendererUnicode.NON_FULL_BLOCKS_COUNT)
        ]

        return (
            ProgressBarRendererUnicode.VBAR,
            "{}{}".format(
                ProgressBarRendererUnicode.BLOCK_FULL * round(full_blocks),
                last_block_chr
            ),
            ProgressBarRendererUnicode.VBAR
        )


class ProgressBarRendererFactory:
    @staticmethod
    def ascii(mark: str = "=") -> ProgressBarRenderer:
        return ProgressBarRendererAscii(mark)

    @staticmethod
    def unicode() -> ProgressBarRenderer:
        return ProgressBarRendererUnicode()

    @staticmethod
    def auto() -> ProgressBarRenderer:
        if is_unicode_supported():
            return ProgressBarRendererFactory.unicode()
        return ProgressBarRendererFactory.ascii()


class FileProgressor:

    # Config of the render of progress bar

    # We will put stuff based on how many space we have.
    # In order of priority we have to show:
    # D    . Description
    # DP   . Percentage
    # DPT  . Transferred (Partial / Total)
    # DPTS . Speed
    # DPTSB. Bar (taking up as much space as possible)

    # D    . "test.bin"
    # DP   . "test.bin  5%"                                   | S0,S4
    # DPT  . "test.bin  5%  10MB/52MB                         | S0,S2,S4
    # DPTS . "test.bin  5%  10MB/52MB  10KB/s                 | S0,S2,S3,S4
    # DPTSB. "test.bin  [====        ] 5%  10MB/52MB  10KB/s  | S0,S1,S2,S3,S4
    #
    # SPACES:         --              -  --         --      --
    #                 S0              S1 S2         S3      S4

    # ----------

    # If there isn't at least PROGRESS_BAR_MIN_INNER_WIDTH, the bar won't be shown
    PROGRESS_BAR_MIN_INNER_WIDTH = 10
    PROGRESS_BAR_MIN_OUTER_WIDTH = PROGRESS_BAR_MIN_INNER_WIDTH + 2

    S0 = 4
    S1 = 1
    S2 = 2
    S3 = 2
    S4 = 0

    LEN_P = 4               # 100%
    LEN_TH = 7              # 654.4KB
    LEN_T = LEN_TH * 2 + 1  # 654.4KB/120.2GB
    LEN_S = 10              # 654.4KB/s
    # ^ It would be 9 but allow 10 chars for
    # the alternative time_instead_speed
    # time_instead_speed:   # 1h 12m 43s

    S_D = S4
    S_DP = S0 + S4
    S_DPT = S0 + S2 + S4
    S_DPTS = S0 + S2 + S3 + S4
    S_DPTSB = S0 + S1 + S2 + S3 + S4

    MIN_P = S_DP + LEN_P
    MIN_PT = S_DPT + LEN_P + LEN_T
    MIN_PTS = S_DPTS + LEN_P + LEN_T + LEN_S
    MIN_PTSB = S_DPTSB + LEN_P + LEN_T + LEN_S + PROGRESS_BAR_MIN_OUTER_WIDTH

    # FMT_D = "{}" + (" " * S4)
    FMT_P = (" " * S0) + "{}" + (" " * S4)
    FMT_PT = (" " * S0) + "{}" + (" " * S2) + "{}" + (" " * S4)
    FMT_PTS = (" " * S0) + "{}" + (" " * S2) + "{}" + (" " * S3) + "{}" + (" " * S4)

    FMT_PTSB = (" " * S0) + "{}" + (" " * S1) + "{}" + (" " * S2) + "{}" + (" " * S3) + "{}" + (" " * S4)

    def __init__(self,
                 total: int, *,
                 description: str,
                 partial: int = 0,
                 ui_fps: float = 20,
                 speed_fps: float = 4,
                 progress_bar_renderer: ProgressBarRenderer = ProgressBarRendererFactory.auto(),
                 color_progress: str = None,
                 color_done: str = None):

        self.description = description
        self.partial = partial
        self.total = total if total else 0
        self.progress_bar_renderer = progress_bar_renderer
        self.color_progress = color_progress
        self.color_done = color_done

        self.ui_period_ns = (1 / ui_fps) * 1e9
        self.speed_period_ns = (1 / speed_fps) * 1e9

        self._first_t = None
        self._last_t = None
        self._last_render_t = None

        self._speed_period_t = None
        self._speed_period_partial = 0

        self._speed_last_period_avg = 0

    def increase(self, amount: int):
        self.update(self.partial + amount)

    # noinspection PyPep8Naming
    def update(self,
               partial: int, *,
               force: bool = False,
               inline: bool = True,
               time_instead_speed: bool = False):
        """
        Updates the progress setting the count to 'partial'.
        If 'force' is True, the line is actually rendered, otherwise the behaviour
        depends on the speed_fps given in init().
        Inline will add a \r at the end of the line, if it is False every update
        will be rendered as new line.
        'time_instead_speed' is useful at the end for show the elapsed time
        instead of the estimated speed.
        """
        partial = partial if partial else 0

        if partial < self.partial:
            log.w("Progress cannot go backward")
            return

        t = time.monotonic_ns()

        # Remind the first update (for render the total time at the end)
        if not self._first_t:
            self._first_t = t

        # Compute speed (apart from the first call)
        if self._last_t:
            # Increase the byte count of the current speed period
            self._speed_period_partial += (partial - self.partial)

            if self._speed_period_t:
                speed_period_delta_t = t - self._speed_period_t

                if speed_period_delta_t > self.speed_period_ns:
                    # New period

                    # Calculate the avg speed
                    self._speed_last_period_avg = self._speed_period_partial * 1e9 / speed_period_delta_t

                    # Reset the sampling variables
                    self._speed_period_partial = 0
                    self._speed_period_t = t
            else:
                # First period
                self._speed_period_t = t

        self.partial = partial
        self._last_t = t

        ratio = self.partial / self.total if self.total > 0 else 1
        percentage = int(100 * ratio)

        # Do not render too fast (stay below FPS)
        # Exceptions:
        # 1. 'force' set to True
        # 2. First update
        if force or not self._last_render_t or \
                (t - self._last_render_t) > self.ui_period_ns:
            self._last_render_t = t

            # Retrieve the terminal size for render properly
            cols, rows = terminal_size()

            D = self.description
            P = str(percentage) + "%"
            T = "{}/{}".format(
                size_str(self.partial).rjust(FileProgressor.LEN_TH),
                size_str(self.total).ljust(FileProgressor.LEN_TH)
            )
            S = ""

            if time_instead_speed:
                S = duration_str_human(round((t - self._first_t) * 1e-9), )
            elif self._speed_last_period_avg:
                S = speed_str(self._speed_last_period_avg)

            # Assign a fixed space to the description part (2/5) and
            # the remaining (3/5) to the other stuff
            D_space = cols * 2 // 5
            remaining_space = cols - D_space

            # Make D fill D_width; eventually strip some part of the description
            E_width = len("...")
            if len(D) > D_space:
                # Not enough space, we have to strip something
                D_head, D_tail = os.path.split(D)

                if len(D_tail) + E_width < D_space:
                    # There is space at least for the tail,
                    # but as much as possible of the head in the remaining space
                    D = D_head[:D_space - len(D_tail) - E_width] + "..." + D_tail
                else:
                    # Quite problematic, we have to strip a part of the tail
                    D = "..." + D_tail[-(D_space - E_width):]

            # assert len(D) <= D_space, f"D = {D} | {len(D)} != {D_space}"
            # log.d("cols                 %d", cols)
            # log.d("D                    %s", D)
            # log.d("D_space              %d", D_space)
            # log.d("remaining_space      %d", remaining_space)

            if remaining_space >= FileProgressor.MIN_PTSB:
                # DPTSB
                # Use as much space as possible for the bar
                progress_bar_inner_width = \
                    remaining_space - (
                            FileProgressor.LEN_P +
                            FileProgressor.LEN_T +
                            FileProgressor.LEN_S +
                            FileProgressor.S_DPTSB +
                            2 * len("|")
                    )
                progress_bar = self._progress_bar_string(progress_bar_inner_width, ratio)

                remaining_space_filling = FileProgressor.FMT_PTSB.format(
                    progress_bar,
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T),
                    S.rjust(FileProgressor.LEN_S)
                )

                # log.d("len(progress_bar_in) %d", progress_bar_inner_width)
                # log.d("len(progress_bar)    %d", progress_bar_inner_width + 2)
                # log.d("P                    %d", len(P.rjust(FileProgressor.LEN_P)))
                # log.d("T                    %d", len(T.rjust(FileProgressor.LEN_T)))
                # log.d("S                    %d", len(S.rjust(FileProgressor.LEN_S)))


            elif remaining_space >= FileProgressor.MIN_PTS:
                remaining_space_filling = FileProgressor.FMT_PTS.format(
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T),
                    S.rjust(FileProgressor.LEN_S)
                )
            # DPT
            elif remaining_space >= FileProgressor.MIN_PT:
                remaining_space_filling = FileProgressor.FMT_PT.format(
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T),
                )
            # DP
            elif remaining_space >= FileProgressor.MIN_P:
                remaining_space_filling = FileProgressor.FMT_P.format(
                    P.rjust(FileProgressor.LEN_P),
                )
            # D
            else:
                remaining_space_filling = ""

            progress_line = \
                D.ljust(D_space) + remaining_space_filling.rjust(remaining_space)

            # assert len(D.ljust(D_space)) == D_space
            # assert len(remaining_space_filling.rjust(remaining_space)) == remaining_space
            # assert len(progress_line) == cols

            print(progress_line, end="\r" if inline else "\n")

    def done(self):
        """ Marks the end of the progress: finalize the line and show the elapsed time """
        self.update(self.total, force=True, inline=False, time_instead_speed=True)

    def _progress_bar_string(self, progress_bar_inner_width: int, progress_ratio: float) -> str:
        """
        Builds the progress bar; of width 'progress_bar_inner_width'
        with a completion that is specified by 'progress_ratio'
        """
        # The inner progress can be built with either
        # 1. A progress mark (e.g. =)
        # 2. Progress blocks, which are UNICODE for create a fancy
        #    fulfilled bar

        prefix, inner, postfix = self.progress_bar_renderer.render(
            progress_bar_inner_width, progress_ratio
        )

        inner = inner.ljust(progress_bar_inner_width)

        if self.partial < self.total and self.color_progress:
            inner = fg(inner, self.color_progress)

        if self.partial == self.total and self.color_done:
            inner = fg(inner, self.color_done)

        return prefix + inner + postfix


if __name__ == "__main__":
    enable_colors()
    get_logger(__name__, root=True).set_verbosity(logging.VERBOSITY_ERROR)

    def simulate_file_progression(name: str, tot: int,
                                  delta_b=4096, delta_t=0.001):

        prog = FileProgressor(tot,
                              description=name,
                              # ui_fps=fps,
                              # speed_fps=sfps,
                              # color_progress=Color.BLUE,
                              # progress_bar_style=ProgressBarStyle.ASCII,
                              # color_done=Color.GREEN
                              )
        part = 0

        while part < tot:
            bs = random.randint(delta_b - 1/2 * delta_b, delta_b + 1/2 * delta_b)
            t =  delta_t + random.random() * delta_t

            part += bs
            time.sleep(t)
            part = min(part, tot)

            prog.update(part)

        prog.done()


    for root, dirs, files in os.walk('shared'):
        for f in files:
            fullpath = os.path.join(root, f)
            size = os.path.getsize(fullpath)
            simulate_file_progression(fullpath, size, delta_b=512, delta_t=0.03)
