import logging
from typing import Optional

from easyshare.common import VERBOSITY_NONE, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO, VERBOSITY_DEBUG, \
    VERBOSITY_MIN, VERBOSITY_MAX
from easyshare.settings import add_setting_callback, Settings
from easyshare.styling import green, blue, yellow, red, is_styling_enabled
from easyshare.utils.mathematics import rangify

ROOT_LOGGER_PATTERN = "__main__"            # the real name of the root logger
ROOT_LOGGER_DISPLAY_NAME = "easyshare"      # the name we'll use to to render the root logger

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
_default_verbosity = None
_log_handler: Optional[logging.StreamHandler] = None


class Logger(logging.Logger):
    """
    Extends the python Logger by adding the aliases e, w, i, d.
    Adds the concept of "verbosity", which is just a more convenient
    name for treat levels (verbosity has a consecutive enumeration).
    """
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
        self._style._fmt = self._lineno_fmt() \
            if (record.levelno == LEVEL_ERROR or record.levelno == LEVEL_WARNING)\
            else self._default_fmt()
        return super().format(record)

    def _default_fmt(self):
        return "%(levelname)s {%(name)s} " + \
               ("%(asctime)s.%(msecs)03d " if self._show_time else "") + \
               "%(message)s"

    def _lineno_fmt(self):
        return "%(levelname)s {%(name)s:%(lineno)d} " + \
               ("%(asctime)s.%(msecs)03d " if self._show_time else "") + \
               "%(message)s"


def init_logging(default_verbosity: int = None):
    """
    Initializes the logger and add the easyshare extension
    (verbosity, short alias for printing) to the Logger.
    If not None, new loggers will be initialized to this level.
    After this call, the root logger is already configured.
    """
    global _initialized
    global _default_verbosity
    global _log_handler

    import sys

    _log_handler = logging.StreamHandler(sys.stderr)
    _log_handler.setFormatter(LoggerFormatter())

    def set_verbosity(logger: logging.Logger, verbosity: int):
        if verbosity not in VERBOSITY_TO_LEVEL:
            verbosity = rangify(verbosity, VERBOSITY_MIN, VERBOSITY_MAX)

        logger.setLevel(VERBOSITY_TO_LEVEL[verbosity])
        logger.verbosity = verbosity

    def set_levels_renderers(_1, _2):
        # print(f"set_levels_renderers, current styling = {is_styling_enabled()}")
        # Aliases
        logging.addLevelName(LEVEL_ERROR, red("[ERROR]"))
        logging.addLevelName(LEVEL_WARNING, yellow("[WARN] "))
        logging.addLevelName(LEVEL_INFO, blue("[INFO] "))
        logging.addLevelName(LEVEL_DEBUG, green("[DEBUG]"))

    set_levels_renderers(None, None)
    logging.Logger.e = logging.Logger.error
    logging.Logger.w = logging.Logger.warning
    logging.Logger.i = logging.Logger.info
    logging.Logger.d = logging.Logger.debug
    logging.Logger.set_verbosity = set_verbosity


    # We can initialize the root logger at this point
    if _initialized is False:
        get_logger()
        # Change the logger verbosity
        add_setting_callback(Settings.VERBOSITY, lambda k,v: get_logger().set_verbosity(v))
        # Eventually reinitialize the renderers
        add_setting_callback(Settings.COLORS, set_levels_renderers)

    _initialized = True
    _default_verbosity = default_verbosity


def get_logger(name: str = ROOT_LOGGER_PATTERN,
               root: bool = False,
               verbosity: int = None) -> Logger:
    """
    Get the logger for 'name', eventually add an handler if the logger is a root logger
    (the responsible for print messages, the child only forwards message to it)
    """
    # Don't call init_logging() even if is attempting...
    # We have to call it manually after checking the colors support

    fetch_name = ROOT_LOGGER_DISPLAY_NAME if ROOT_LOGGER_PATTERN in name else name

    logger: logging.Logger = logging.getLogger(fetch_name)
    if ROOT_LOGGER_PATTERN in name or root:
        if not logger.hasHandlers():
            logger.addHandler(_log_handler)

    verb = verbosity if verbosity is not None else _default_verbosity

    if verb is not None:
        # Set the level corresponding to the explicit verbosity
        level = VERBOSITY_TO_LEVEL[rangify(verb, VERBOSITY_MIN, VERBOSITY_MAX)]
        logger.setLevel(level)
        logger.verbosity = verb
    else:
        # Keep the default level and make verbosity consistent with the level
        level = logger.getEffectiveLevel()
        logger.verbosity = LEVEL_TO_VERBOSITY[rangify(level, LEVEL_DEBUG, LEVEL_FATAL)]
    return logger


def get_logger_silent(name, root: bool = False):
    """ Get a logger for 'name' but set the verbosity to VERBOSITY_MIN """
    return get_logger(name, root, verbosity=VERBOSITY_MIN)
