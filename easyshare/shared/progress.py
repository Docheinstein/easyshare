import math
import time
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple

from easyshare.logging import get_logger
from easyshare.utils.colors import fg, Color, enable_colors
from easyshare.utils.env import is_unicode_supported, terminal_size
from easyshare.utils.os import M, size_str
from easyshare.utils.time import duration_str


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

    SIZE_PREFIXES = ("B", "KB", "MB", "GB")
    SPEED_PREFIXES = ("B/s", "KB/s", "MB/s", "GB/s")

    TIME_FORMATS = ("{}h ", "{}m ", "{}s")

    # Config of the render of progress bar

    # We will put stuff based on how many space we have.
    # In order of priority we have to show:
    # W    . What
    # WP   . Percentage
    # WPT  . Transferred (Partial / Total)
    # WPTS . Speed
    # WPTSB. Bar (taking up as much space as possible)

    # W    . "test.bin"
    # WP   . "test.bin  5%"                                   | S0,S4
    # WPT  . "test.bin  5%  10MB/52MB                         | S0,S2,S4
    # WPTS . "test.bin  5%  10MB/52MB  10KB/s                 | S0,S2,S3,S4
    # WPTSB. "test.bin  [====        ] 5%  10MB/52MB  10KB/s  | S0,S1,S2,S3,S4
    #
    # SPACES:         --              -  --         --      --
    #                 S0              S1 S2         S3      S4

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

    S_W = S4
    S_WP = S0 + S4
    S_WPT = S0 + S2 + S4
    S_WPTS = S0 + S2 + S3 + S4
    S_WPTSB = S0 + S1 + S2 + S3 + S4

    MIN_P = S_WP + LEN_P
    MIN_PT = S_WPT + LEN_P + LEN_T
    MIN_PTS = S_WPTS + LEN_P + LEN_T + LEN_S
    MIN_PTSB = S_WPTSB + LEN_P + LEN_T + LEN_S + PROGRESS_BAR_MIN_OUTER_WIDTH

    FMT_W = "{}" + (" " * S4)
    FMT_WP = "{}" + (" " * S0) + "{}" + (" " * S4)
    FMT_WPT = "{}" + (" " * S0) + "{}" + (" " * S2) + "{}"\
              + (" " * S4)
    FMT_WPTS = "{}" + (" " * S0) + "{}" + (" " * S2) + "{}" + (" " * S3) + "{}" + (" " * S4)

    FMT_WPTSB = "{}" + (" " * S0) + "{}" + (" " * S1) + "{}" + (" " * S2) + "{}" + (" " * S3) + "{}" + (" " * S4)

    def __init__(self,
                 total: int, *,
                 description: str,
                 partial: int = 0,
                 ui_fps: float = 20,
                 speed_fps: float = 4,
                 progress_bar_renderer: ProgressBarRenderer = ProgressBarRendererFactory.auto(),
                 color_progress: Color = None,
                 color_done: Color = None):

        self.description = description
        self.partial = partial
        self.total = total if total else 0
        self.ui_fps = ui_fps
        self.speed_fps = speed_fps
        self.progress_bar_renderer = progress_bar_renderer
        self.color_progress = color_progress
        self.color_done = color_done

        self.ui_period_ns = (1 / ui_fps) * 1e9
        self.speed_period_ns = (1 / speed_fps) * 1e9

        self.first_t = None
        self.last_t = None
        self.last_render_t = None

        self.speed_period_t = None
        self.speed_period_partial = 0

        self.speed_last_period_avg = 0

    def increase(self, amount: int):
        self.update(self.partial + amount)

    # noinspection PyPep8Naming
    def update(self,
               partial: int, *,
               force: bool = False,
               inline: bool = True,
               time_instead_speed: bool = False):
        partial = partial if partial else 0

        if partial < self.partial:
            log.w("Progress cannot go backward")
            return

        t = time.monotonic_ns()

        # Remind the first update (for render the total time at the end)
        if not self.first_t:
            self.first_t = t

        # Compute speed (apart from the first call)
        if self.last_t:
            # Increase the byte count of the current speed period
            self.speed_period_partial += (partial - self.partial)

            if self.speed_period_t:
                speed_period_delta_t = t - self.speed_period_t

                if speed_period_delta_t > self.speed_period_ns:
                    # New period

                    # Calculate the avg speed
                    self.speed_last_period_avg = self.speed_period_partial * 1e9 / speed_period_delta_t

                    # Reset the sampling variables
                    self.speed_period_partial = 0
                    self.speed_period_t = t
            else:
                # First period
                self.speed_period_t = t

        self.partial = partial
        self.last_t = t

        ratio = self.partial / self.total if self.total > 0 else 1
        percentage = int(100 * ratio)

        # Do not render too fast (stay below FPS)
        # Exceptions:
        # 1. 'force' set to True
        # 2. First update
        if force or not self.last_render_t or \
                (t - self.last_render_t) > self.ui_period_ns:
            self.last_render_t = t

            # Retrieve the terminal size for render properly
            cols, rows = terminal_size()

            W = self.description
            P = str(percentage) + "%"
            T = "{}/{}".format(
                size_str(self.partial, prefixes=FileProgressor.SIZE_PREFIXES).rjust(FileProgressor.LEN_TH),
                size_str(self.total, prefixes=FileProgressor.SIZE_PREFIXES).ljust(FileProgressor.LEN_TH)
            )
            S = ""

            if time_instead_speed:
                S = duration_str(round((t - self.first_t) * 1e-9),
                                 fixed=False, formats=FileProgressor.TIME_FORMATS)
            elif self.speed_last_period_avg:
                S = size_str(self.speed_last_period_avg, prefixes=FileProgressor.SPEED_PREFIXES)

            Wlen = len(W)

            # WPTSB
            if cols >= Wlen + FileProgressor.MIN_PTSB:
                # Use as much space as possible for the bar
                progress_bar_inner_width = \
                    cols - (Wlen + FileProgressor.LEN_P +
                            FileProgressor.LEN_T + FileProgressor.LEN_S +
                            FileProgressor.S_WPTSB + 2 * len("|"))

                progress_bar = self._progress_bar_string(progress_bar_inner_width, ratio)

                progress_line = FileProgressor.FMT_WPTSB.format(
                    W,
                    progress_bar,
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T),
                    S.rjust(FileProgressor.LEN_S)
                )
            # WPTS
            elif cols >= Wlen + FileProgressor.MIN_PTS:
                progress_line = FileProgressor.FMT_WPTS.format(
                    W.ljust(cols - FileProgressor.MIN_PTS),
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T),
                    S.rjust(FileProgressor.LEN_S)
                )
            # WPT
            elif cols >= Wlen + FileProgressor.MIN_PT:
                progress_line = FileProgressor.FMT_WPT.format(
                    W.ljust(cols - FileProgressor.MIN_PT),
                    P.rjust(FileProgressor.LEN_P),
                    T.rjust(FileProgressor.LEN_T)
                )
            # WP
            elif cols >= Wlen + FileProgressor.MIN_P:
                progress_line = FileProgressor.FMT_WP.format(
                    W.ljust(cols - FileProgressor.MIN_P),
                    P.rjust(FileProgressor.LEN_P)
                )
            # W
            else:
                progress_line = FileProgressor.FMT_W.format(W)

            print(progress_line, end="\r" if inline else "\n")

    def done(self):
        self.update(self.total, force=True, inline=False, time_instead_speed=True)

    def _progress_bar_string(self, progress_bar_inner_width: int, progress_ratio: float) -> str:
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

    def simulate_file_progression(name: str, tot: int,
                                  fps=2, sfps=2,
                                  delta_b=4096, delta_t=0.001):

        prog = FileProgressor(tot,
                              description=name,
                              ui_fps=fps,
                              speed_fps=sfps,
                              color_progress=Color.BLUE,
                              # progress_bar_style=ProgressBarStyle.ASCII,
                              color_done=Color.GREEN)
        part = 0

        while part < tot:
            bs = random.randint(delta_b, delta_b * 12)
            t =  delta_t + random.random() * delta_t

            part += bs
            time.sleep(t)

            prog.update(part)

        prog.done()


    simulate_file_progression("test.bin", 100 * M, fps=20, sfps=2,
                              delta_b=409, delta_t=0.001)

