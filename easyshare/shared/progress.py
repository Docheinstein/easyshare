import time
import random

from easyshare.shared.log import w
from easyshare.utils.colors import fg, Color, init_colors
from easyshare.utils.os import M, size_str, term_size
from easyshare.utils.time import duration_str


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
    PROGRESS_BAR_MIN_OUTER_WIDTH = len("[") + PROGRESS_BAR_MIN_INNER_WIDTH + len("]")

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
    FMT_WPTSB = "{}" + (" " * S0) + "[{}]" + (" " * S1) + "{}" + (" " * S2) + "{}" + (" " * S3) + "{}" + (" " * S4)

    def __init__(self, what: str, total: int, *,
                 partial: int = 0,
                 fps: float = 2,
                 progress_mark: str = "=",
                 progress_color: Color = None,
                 done_color: Color = None):
        self.what = what
        self.partial = partial
        self.total = total
        self.fps = fps
        self.period_ns = (1 / fps) * 1e9
        self.progress_mark = progress_mark
        self.progress_color = progress_color
        self.done_color = done_color

        self.first_t = None
        self.last_t = None
        self.last_render_t = None

        self.speed_period_t = None
        self.speed_period_avg = 0
        self.speed_period_samples = 0

    def increase(self, amount: int):
        self.update(self.partial + amount)

    # noinspection PyPep8Naming
    def update(self, partial: int, *,
               force: bool = False,
               inline: bool = True,
               time_instead_speed: bool = False):
        t = time.monotonic_ns()

        # Remind the first update (for render the total time at the end)
        if not self.first_t:
            self.first_t = t

        if partial < self.partial:
            w("Progress cannot go backward")
            return

        # Compute speed (apart from the first call)
        speed = None

        if self.last_t:
            # Compute delta time
            instant_speed = int((partial - self.partial) * 1e9 /
                        (t - self.last_t))

            # Do an average with the speed of the current period
            # (the period depends on the fps)
            if not self.speed_period_t or \
                    (t - self.speed_period_t) > self.period_ns:
                # New period: reset the speed avg
                self.speed_period_t = t
                self.speed_period_samples = 0
                self.speed_period_avg = 0

            self.speed_period_avg = \
                (self.speed_period_samples * self.speed_period_avg + instant_speed) // \
                (self.speed_period_samples + 1)

            speed = self.speed_period_avg

            self.speed_period_samples += 1

        self.last_t = t
        self.partial = partial

        ratio = self.partial / self.total
        percentage = int(100 * ratio)

        # Do not render too fast (stay below FPS)
        # Exceptions:
        # 1. 'force' set to True
        # 2. First update
        if force or not self.last_render_t or \
                (t - self.last_render_t) > self.period_ns:
            self.last_render_t = t

            # Retrieve the terminal size for render properly
            cols, rows = term_size()

            W = self.what
            P = str(percentage) + "%"
            T = "{}/{}".format(
                size_str(self.partial, prefixes=FileProgressor.SIZE_PREFIXES).rjust(FileProgressor.LEN_TH),
                size_str(self.total, prefixes=FileProgressor.SIZE_PREFIXES).ljust(FileProgressor.LEN_TH)
            )
            S = ""
            if time_instead_speed:
                S = duration_str(round((t - self.first_t) * 1e-9),
                                 fixed=False, formats=FileProgressor.TIME_FORMATS)
            elif speed:
                S = size_str(speed, prefixes=FileProgressor.SPEED_PREFIXES)

            Wlen = len(W)

            # WPTSB
            if cols >= Wlen + FileProgressor.MIN_PTSB:
                # Use as much space as possible for the bar
                progress_bar_inner_width = \
                    cols - (Wlen + FileProgressor.LEN_P +
                            FileProgressor.LEN_T + FileProgressor.LEN_S +
                            FileProgressor.S_WPTSB + len("[]"))

                progress_bar_inner = \
                    (self.progress_mark * int(ratio * progress_bar_inner_width))\
                        .ljust(progress_bar_inner_width)

                if self.partial < self.total and self.progress_color:
                    progress_bar_inner = fg(progress_bar_inner, self.progress_color)
                elif self.partial == self.total and self.done_color:
                    progress_bar_inner = fg(progress_bar_inner, self.done_color)

                progress_line = FileProgressor.FMT_WPTSB.format(
                    W,
                    progress_bar_inner,
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
                progress_line = FileProgressor.FMT_WPT.format(
                    W.ljust(cols - FileProgressor.MIN_P),
                    P.rjust(FileProgressor.LEN_P)
                )
            # W
            else:
                progress_line = FileProgressor.FMT_W.format(W)

            print(progress_line, end="\r" if inline else "\n")

    def done(self):
        self.update(self.total, force=True, inline=False, time_instead_speed=True)


if __name__ == "__main__":
    init_colors()

    def simulate_file_progression(name: str, tot: int, fps: float = 2):
        prog = FileProgressor(name, tot,
                              fps=fps,
                              progress_mark="*",
                              progress_color=Color.BLUE,
                              done_color=Color.GREEN)
        part = 0
        while part < tot:
            delta_b = random.randint(4096, 4096 * 12)
            delta_t = random.randint(1, 5) * 0.001
            time.sleep(delta_t)
            prog.update(part)
            part += delta_b
        prog.done()

    simulate_file_progression("test.bin", 5 * M, fps=20)
    # simulate_file_progression("test.bin", 100 * M)

