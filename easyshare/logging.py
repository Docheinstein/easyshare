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

LEVEL_ERROR = logging.ERROR
LEVEL_WARNING = logging.WARNING
LEVEL_INFO = logging.INFO
LEVEL_DEBUG = logging.DEBUG

VERBOSITY_TO_LEVEL = {
    VERBOSITY_NONE: None,
    VERBOSITY_ERROR: LEVEL_ERROR,
    VERBOSITY_WARNING: VERBOSITY_WARNING,
    VERBOSITY_INFO: VERBOSITY_INFO,
    VERBOSITY_DEBUG: VERBOSITY_DEBUG,
}

logging.addLevelName(LEVEL_ERROR,   styled("[ERROR]", fg=Color.RED))
logging.addLevelName(LEVEL_WARNING, styled("[WARN] ", fg=Color.YELLOW))
logging.addLevelName(LEVEL_INFO,    styled("[INFO] ", fg=Color.BLUE))
logging.addLevelName(LEVEL_DEBUG,   styled("[DEBUG]", fg=Color.MAGENTA))


class Logger(logging.Logger):
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


def get_logger(name: str, level=LEVEL_WARNING, output=sys.stdout) -> Logger:
    logger: logging.Logger = logging.getLogger(name)

    # Aliases
    def set_verbosity(self, verbosity: int):
        if verbosity not in VERBOSITY_TO_LEVEL:
            verbosity = rangify(verbosity, VERBOSITY_DEBUG, VERBOSITY_NONE)

        if verbosity:
            self.disabled = False
            self.setLevel(verbosity)
        else:
            self.disabled = True

    logging.Logger.e = logger.error
    logging.Logger.w = logger.warning
    logging.Logger.i = logger.info
    logging.Logger.d = logger.debug
    logging.Logger.set_verbosity = set_verbosity

    # Message formatting

    handler = logging.StreamHandler(output)

    formatter = logging.Formatter(
        fmt="%(levelname)s {%(name)s} %(asctime)s.%(msecs)03d %(message)s",
        datefmt="%H:%M:%S"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.setLevel(level)


    return logger


if __name__ == "__main__":
    log = get_logger(__name__)
    log.e("Hello")
