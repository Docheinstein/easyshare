import time

from easyshare.consts import ansi
from easyshare.styling import enable_styling
from easyshare.utils.env import terminal_size
from easyshare.utils.progress import Progressor


class SimpleProgressor(Progressor):

    def _progress_string(self, progress_ratio: float, t: int):
        cols, rows = self._safe_terminal_size()
        # print("ratio: ", progress_ratio)
        return self._progress_bar_string(
            progress_bar_inner_width=cols - 2,
            progress_ratio=progress_ratio
        )


if __name__ == "__main__":
    enable_styling()
    with SimpleProgressor(10) as pbar:
        for i in range(1, 10):
            pbar.update(i)
            time.sleep(1)
