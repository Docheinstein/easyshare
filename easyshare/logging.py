import logging
import sys

from easyshare.utils.colors import styled, Color
from easyshare.utils.math import rangify

ROOT_LOGGER_NAME = "easyshare"

VERBOSITY_NONE = 0
VERBOSITY_ERROR = 1
VERBOSITY_WARNING = 2
VERBOSITY_INFO = 3
VERBOSITY_DEBUG = 4

VERBOSITY_MIN = VERBOSITY_NONE
VERBOSITY_MAX = VERBOSITY_DEBUG
VERBOSITY_DEFAULT = VERBOSITY_INFO

LEVEL_FATAL = logging.FATAL
LEVEL_ERROR = logging.ERROR
LEVEL_WARNING = logging.WARNING
LEVEL_INFO = logging.INFO
LEVEL_DEBUG = logging.DEBUG

VERBOSITY_TO_LEVEL = {
    VERBOSITY_NONE: LEVEL_FATAL,
    VERBOSITY_ERROR: LEVEL_ERROR,
    VERBOSITY_WARNING: LEVEL_WARNING,
    VERBOSITY_INFO: LEVEL_INFO,
    VERBOSITY_DEBUG: LEVEL_DEBUG,
}


LEVEL_TO_VERBOSITY = {
    LEVEL_FATAL: VERBOSITY_NONE,
    LEVEL_ERROR: VERBOSITY_ERROR,
    LEVEL_WARNING: VERBOSITY_WARNING,
    LEVEL_INFO: VERBOSITY_INFO,
    LEVEL_DEBUG: VERBOSITY_DEBUG,
}


# Aliases


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


class LoggerFormatter(logging.Formatter):

    def __init__(self, show_time: bool = False):
        self._show_time = show_time
        super().__init__(
            fmt=self._default_fmt(),
            datefmt="%H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        self._style._fmt = self._error_fmt() \
            if record.levelno == LEVEL_ERROR else self._default_fmt()
        return super().format(record)

    def _default_fmt(self):
        return "%(levelname)s {%(name)s} " + \
               ("%(asctime)s.%(msecs)03d " if self._show_time else "") + \
               "%(message)s"

    def _error_fmt(self):
        return "%(levelname)s {%(name)s:%(lineno)d} " + \
               ("%(asctime)s.%(msecs)03d " if self._show_time else "") + \
               "%(message)s"


def _set_verbosity(logger: logging.Logger, verbosity: int):
    if verbosity not in VERBOSITY_TO_LEVEL:
        verbosity = rangify(verbosity, VERBOSITY_MIN, VERBOSITY_MAX)

    logger.setLevel(VERBOSITY_TO_LEVEL[verbosity])
    logger.verbosity = verbosity


logging.addLevelName(LEVEL_ERROR,   styled("[ERROR]", fg=Color.RED))
logging.addLevelName(LEVEL_WARNING, styled("[WARN] ", fg=Color.YELLOW))
logging.addLevelName(LEVEL_INFO,    styled("[INFO] ", fg=Color.BLUE))
logging.addLevelName(LEVEL_DEBUG,   styled("[DEBUG]", fg=Color.GREEN))


logging.Logger.e = logging.Logger.error
logging.Logger.w = logging.Logger.warning
logging.Logger.i = logging.Logger.info
logging.Logger.d = logging.Logger.debug
logging.Logger.set_verbosity = _set_verbosity

logging_handler = logging.StreamHandler(sys.stdout)
logging_handler.setFormatter(LoggerFormatter())

# logging.basicConfig(stream=sys.stderr, format="[%(asctime)s,%(name)s,%(levelname)s] %(message)s")


def get_logger(name: str = ROOT_LOGGER_NAME) -> Logger:
    logger: logging.Logger = logging.getLogger(name)
    if name == ROOT_LOGGER_NAME:
        logger.addHandler(logging_handler)
    logger.verbosity = LEVEL_TO_VERBOSITY[logger.getEffectiveLevel()]
    return logger


if __name__ == "__main__":
    log = get_logger(__name__)
    log.e("Hello")
