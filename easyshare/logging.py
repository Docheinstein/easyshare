import logging
import sys

from easyshare.utils.colors import styled, Color
from easyshare.utils.math import rangify

VERBOSITY_NONE = 0
VERBOSITY_ERROR = 1
VERBOSITY_WARNING = 2
VERBOSITY_INFO = 3
VERBOSITY_DEBUG = 4

VERBOSITY_MIN = VERBOSITY_NONE
VERBOSITY_MAX = VERBOSITY_DEBUG
VERBOSITY_DEFAULT = VERBOSITY_INFO

LEVEL_ERROR = logging.ERROR
LEVEL_WARNING = logging.WARNING
LEVEL_INFO = logging.INFO
LEVEL_DEBUG = logging.DEBUG

VERBOSITY_TO_LEVEL = {
    VERBOSITY_NONE: logging.FATAL,
    VERBOSITY_ERROR: LEVEL_ERROR,
    VERBOSITY_WARNING: LEVEL_WARNING,
    VERBOSITY_INFO: LEVEL_INFO,
    VERBOSITY_DEBUG: LEVEL_DEBUG,
}

logging.addLevelName(LEVEL_ERROR,   styled("[ERROR]", fg=Color.RED))
logging.addLevelName(LEVEL_WARNING, styled("[WARN] ", fg=Color.YELLOW))
logging.addLevelName(LEVEL_INFO,    styled("[INFO] ", fg=Color.BLUE))
logging.addLevelName(LEVEL_DEBUG,   styled("[DEBUG]", fg=Color.MAGENTA))


class Logger(logging.Logger):
    @property
    def verbosity(self):
        return 0

    def e(self, msg, *args, **kwargs):
        pass

    def w(self, msg, *args, **kwargs):
        pass

    def i(self, msg, *args, **kwargs):
        pass

    def d(self, msg, *args, **kwargs):
        pass

    def set_verbosity(self, verbosity: int):
        pass


def get_logger(name: str = "easyshare") -> Logger:
    logger: Logger = logging.getLogger(name)
    # logger.set_verbosity(verbosity)
    return logger


# Aliases
def _set_verbosity(self, verbosity: int):
    if verbosity not in VERBOSITY_TO_LEVEL:
        verbosity = rangify(verbosity, VERBOSITY_MIN, VERBOSITY_MAX)

    self.setLevel(VERBOSITY_TO_LEVEL[verbosity])
    self.verbosity = verbosity


logging.Logger.e = logging.Logger.error
logging.Logger.w = logging.Logger.warning
logging.Logger.i = logging.Logger.info
logging.Logger.d = logging.Logger.debug
logging.Logger.set_verbosity = _set_verbosity

logging.basicConfig(
    format="%(levelname)s {%(name)s} %(asctime)s.%(msecs)03d %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout
)

if __name__ == "__main__":
    log = get_logger(__name__)
    log.e("Hello")
