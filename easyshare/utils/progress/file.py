import os
import time
import random

from easyshare.logging import get_logger
from easyshare.styling import enable_colors
from easyshare.utils.env import terminal_size
from easyshare.utils.measures import duration_str_human, size_str, speed_str
from easyshare.utils.progress import Progressor

log = get_logger(__name__)


class FileProgressor(Progressor):

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
                 **kwargs):
        super().__init__(total, **kwargs)
        self._description = description

    # noinspection PyPep8Naming
    def _progress_string(self, progress_ratio: float, t: int):
        # Retrieve the terminal size for render properly
        percentage = int(100 * progress_ratio)

        cols, rows = terminal_size()

        D = self._description

        P = str(percentage) + "%"
        T = "{}/{}".format(
            size_str(self.partial).rjust(FileProgressor.LEN_TH),
            size_str(self.total).ljust(FileProgressor.LEN_TH)
        )
        S = ""

        if self._done:
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
            progress_bar = self._progress_bar_string(progress_bar_inner_width, progress_ratio)

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

        progress_line = D.ljust(D_space) + remaining_space_filling.rjust(remaining_space)

        return progress_line


if __name__ == "__main__":
    enable_colors()

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


    for root, dirs, files in os.walk('/home/stefano/Temp/test'):
        for f in files:
            fullpath = os.path.join(root, f)
            size = os.path.getsize(fullpath)
            simulate_file_progression(fullpath, size, delta_b=512, delta_t=0.3)
