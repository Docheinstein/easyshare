import logging
import sys

from easyshare.utils.types import is_int

LOGGING_CRITICAL = logging.CRITICAL
LOGGING_ERROR = logging.ERROR
LOGGING_WARNING = logging.WARNING
LOGGING_INFO = logging.INFO
LOGGING_VERBOSE = logging.DEBUG + 1
LOGGING_DEBUG = logging.DEBUG


VERBOSITY_NONE = 0
VERBOSITY_ERROR = 1
VERBOSITY_WARNING = 2
VERBOSITY_INFO = 3
VERBOSITY_VERBOSE = 4
VERBOSITY_DEBUG = 5
VERBOSITY_MAX = VERBOSITY_DEBUG


logger = None
verbosity = None


def e(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)


def w(msg, *args, **kwargs):
    logger.warn(msg, *args, **kwargs)


def i(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)


def v(msg, *args, **kwargs):
    logger.verbose(msg, *args, **kwargs)


def d(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)


def init_logging(verb: int):
    global verbosity

    VERBOSITY_MAP = {
        VERBOSITY_NONE: None,
        VERBOSITY_ERROR: LOGGING_ERROR,
        VERBOSITY_WARNING: LOGGING_WARNING,
        VERBOSITY_INFO: LOGGING_INFO,
        VERBOSITY_VERBOSE: LOGGING_VERBOSE,
        VERBOSITY_DEBUG: LOGGING_DEBUG
    }

    if not is_int(verb):
        return None

    if verb not in VERBOSITY_MAP:
        verb = max(min(verb, VERBOSITY_DEBUG), VERBOSITY_NONE)

    verbosity = verb

    _init_python_logging(enabled=verbosity > VERBOSITY_NONE,
                         level=VERBOSITY_MAP.get(verbosity))


def get_verbosity() -> int:
    global verbosity
    return verbosity


def _init_python_logging(enabled: bool, level: int, output=sys.stdout):
    """ Initializes logging. """
    global logger

    if not logger:
        logger = logging.getLogger("easyshare")

        logging_handler = logging.StreamHandler(output)
        logging_handler.setFormatter(logging.Formatter(
            fmt="[%(levelname)s] %(asctime)s %(message)s",
            datefmt="%d/%m/%y %H:%M:%S"))

        logger.addHandler(logging_handler)

        logging.addLevelName(LOGGING_VERBOSE, "VERBOSE")

        def verbose(self, message, *args, **kws):
            if self.isEnabledFor(LOGGING_VERBOSE):
                self.log(LOGGING_VERBOSE, message, *args, **kws)

        logging.Logger.verbose = verbose

    if not enabled:
        logger.disabled = True
    elif level:
        logger.disabled = False
        logger.setLevel(level=level)
