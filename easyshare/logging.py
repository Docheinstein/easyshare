import logging
import sys

from easyshare.styling import green, blue, yellow, red
from easyshare.utils.mathematics import rangify

ROOT_LOGGER_NAME = "__main__"
ROOT_LOGGER_DISPLAY_NAME = "easyshare"

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

_initialized = False


class Logger(logging.Logger):
    @property
    def verbosity(self):
        return

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


_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(LoggerFormatter())

def init_logging():
    """
    Initializes the logger and add the easyshare extension
    (verbosity, short alias for printing) to the Logger
    """
    global _initialized

    if _initialized:
        return

    def set_verbosity(logger: logging.Logger, verbosity: int):
        if verbosity not in VERBOSITY_TO_LEVEL:
            verbosity = rangify(verbosity, VERBOSITY_MIN, VERBOSITY_MAX)

        logger.setLevel(VERBOSITY_TO_LEVEL[verbosity])
        logger.verbosity = verbosity

    # Aliases
    logging.addLevelName(LEVEL_ERROR, red("[ERROR]"))
    logging.addLevelName(LEVEL_WARNING, yellow("[WARN] "))
    logging.addLevelName(LEVEL_INFO, blue("[INFO] "))
    logging.addLevelName(LEVEL_DEBUG, green("[DEBUG]"))

    logging.Logger.e = logging.Logger.error
    logging.Logger.w = logging.Logger.warning
    logging.Logger.i = logging.Logger.info
    logging.Logger.d = logging.Logger.debug
    logging.Logger.set_verbosity = set_verbosity

    _initialized = True


def get_logger(name: str = ROOT_LOGGER_NAME,
               root: bool = False,
               verbosity: int = None) -> Logger:
    """
    Get the logger for 'name', eventually add an handler if the logger is a root logger
    (the responsible for print messages, the child only forwards message to it)
    """
    # Don't call init_logging() even if is attempting...
    # We have to call it manually after checking the colors support

    fetch_name = ROOT_LOGGER_DISPLAY_NAME if name == ROOT_LOGGER_NAME else name

    logger: logging.Logger = logging.getLogger(fetch_name)
    if name == ROOT_LOGGER_NAME or root:
        logger.addHandler(_log_handler)

    if verbosity is not None:
        # Set the level corresponding to the explicit verbosity
        level = VERBOSITY_TO_LEVEL[rangify(verbosity, VERBOSITY_MIN, VERBOSITY_MAX)]
        logger.setLevel(level)
        logger.verbosity = verbosity
    else:
        # Keep the default level and make verbosity consistent with the level
        level = logger.getEffectiveLevel()
        logger.verbosity = LEVEL_TO_VERBOSITY[rangify(level, LEVEL_DEBUG, LEVEL_FATAL)]
    return logger


def get_logger_silent(name, root: bool = False):
    """ Get a logger for 'name' but set the verbosity to VERBOSITY_MIN """
    return get_logger(name, root, verbosity=VERBOSITY_MIN)