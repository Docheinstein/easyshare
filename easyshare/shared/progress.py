import time
import random

from easyshare.shared.log import w
from easyshare.utils.os import M, size_str


class FileProgressor:

    MIN_SPEED_COMPUTE_THRESHOLD_NS = 1e9

    def __init__(self, what: str, total: int, *,
                 partial: int = 0,
                 mark="="):
        self.what = what
        self.partial = partial
        self.total = total
        self.mark = mark
        self.last_t = None
        self.last_speed_compute_t = None
        self.speed = None

    def increase(self, amount: int):
        self.update(self.partial + amount)

    def update(self, partial: int):
        if partial < self.partial:
            w("Progress cannot go backward")
            return

        t = time.monotonic_ns()

        delta_amount = partial - self.partial

        self.partial = partial

        if self.last_t and (
                not self.last_speed_compute_t or
                (self.last_speed_compute_t + FileProgressor.MIN_SPEED_COMPUTE_THRESHOLD_NS < t)):

            # Compute delta time (apart from the first call)
            delta_t = t - self.last_t
            self.last_speed_compute_t = t
            self.speed = int(delta_amount / (delta_t * 1e-9))

        self.last_t = t

        ratio = self.partial / self.total
        percentage = int(100 * ratio)

        LEN = 50

        print("{} [{}] {}%   {}/{}   {}/s".format(
            self.what or "",
            (self.mark * int(ratio * LEN)).ljust(LEN),
            percentage,
            size_str(self.partial, identifiers=("B", "KB", "MB", "GB")),
            size_str(self.total, identifiers=("B", "KB", "MB", "GB")),
            size_str(self.speed, identifiers=("B", "KB", "MB", "GB")) if self.speed else "",
        ), end="\r")

    # @staticmethod
    # def display(what: str, partial: int, total: int, delta_t):


if __name__ == "__main__":
    prog = FileProgressor("test.bin", 100 * M)
    for i in range(0, 100 * M, 1024):
        time.sleep(random.randint(1, 5) * 0.0001)
        prog.update(i)
    print("Finished")
