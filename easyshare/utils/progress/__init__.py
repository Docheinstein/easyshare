import math
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple

from easyshare.common import easyshare_setup
from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.styling import fg
from easyshare.utils.env import is_unicode_supported

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

    def __init__(self, mark: str = "=", prefix = "[", postfix: str = "]"):
        self._prefix = prefix
        self._mark = mark
        self._postfix = postfix

    def render(self, inner_width: int, progress_ratio: float) -> Tuple[str, str, str]:
        return (
            self._prefix,
            "{}".format(
                self._mark * int(progress_ratio * inner_width)
            ),
            self._postfix
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
    def ascii(mark: str = "=", prefix: str = "[", postfix: str = "]") -> ProgressBarRenderer:
        return ProgressBarRendererAscii(mark, prefix, postfix)

    @staticmethod
    def unicode() -> ProgressBarRenderer:
        return ProgressBarRendererUnicode()

    @staticmethod
    def auto() -> ProgressBarRenderer:
        if is_unicode_supported():
            return ProgressBarRendererFactory.unicode()
        return ProgressBarRendererFactory.ascii()

class Progressor(ABC):

    def __init__(self,
                 total: int, *,
                 partial: int = 0,
                 ui_fps: float = 20,
                 speed_fps: float = 4,
                 progress_bar_renderer: ProgressBarRenderer = ProgressBarRendererFactory.auto(),
                 color_progress: str = None,
                 color_success: str = None,
                 color_error: str = None
                 ):
        self.partial = partial
        self.total = total if total else 0
        self.progress_bar_renderer = progress_bar_renderer
        self.color_progress = color_progress
        self.color_success = color_success
        self.color_error = color_error

        self.ui_period_ns = (1 / ui_fps) * 1e9
        self.speed_period_ns = (1 / speed_fps) * 1e9

        self._first_t = None
        self._last_t = None
        self._last_render_t = None

        self._speed_period_t = None
        self._speed_period_partial = 0

        self._speed_last_period_avg = 0

        # success True => job finished OK
        # success False => job finished FAILED
        self._success = None

    def increase(self, amount: int):
        self.update(self.partial + amount)

    # noinspection PyPep8Naming
    def update(self,
               partial: int, *,
               force: bool = False,
               inline: bool = True,
               success: bool = None):
        """
        Updates the progress setting the count to 'partial'.
        If 'force' is True, the line is actually rendered, otherwise the behaviour
        depends on the speed_fps given in init().
        Inline will add a \r at the end of the line, if it is False every update
        will be rendered as new line.
        """

        if success is not None:
            if self._success is not None:
                return
            self._success = success

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

        # Do not render too fast (stay below FPS)
        # Exceptions:
        # 1. 'force' set to True
        # 2. First update
        if force or not self._last_render_t or \
                (t - self._last_render_t) > self.ui_period_ns:
            self._last_render_t = t

            progress_line = self._progress_string(ratio, t)

            # The \r at the begin prevents ^C from being print when a job interrupted
            # The \r at the end is needed if something else is printed during
            # the progress (so that it will overwrite the bar, and we will render
            # it again the next iter)
            # \r should work as well (since we write always a full line)
            print(ansi.RESET_LINE + progress_line, end="" if inline else "\n", flush=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.success()

    def success(self):
        self.update(self.total, force=True, inline=False, success=True)

    def error(self, completed: bool = False):
        self.update( self.total if completed else self.partial, force=True, inline=False, success=False)

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

        if self._success is None:
            if self.partial < self.total:
                inner = fg(inner, self.color_progress)
            # else:
                # Should not happen, consider this as a success
                # inner = fg(inner, self.color_success)
                # pass
        else:
            if self._success:
                inner = fg(inner, self.color_success)
            else:
                inner = fg(inner, self.color_error)

        return prefix + inner + postfix

    @abstractmethod
    def _progress_string(self, progress_ratio: float, t: int):
        pass

if __name__ == "__main__":
    easyshare_setup()

