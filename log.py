import logging
import sys

from args import Args
from conf import LoggingLevels


def init_logging_from_args(args: Args, verbose_arguments):
    VERBOSE_SEVERITY_MAP = {
        0: None,
        1: LoggingLevels.INFO,
        2: LoggingLevels.DEBUG,
        3: LoggingLevels.TRACE
    }

    verbose_severity = args.get_mparams_count(verbose_arguments)

    if verbose_severity < len(VERBOSE_SEVERITY_MAP):
        # The the corresponding level
        verbose_level = VERBOSE_SEVERITY_MAP[verbose_severity]
    else:
        # Take the last one level (most verbose)
        verbose_level = VERBOSE_SEVERITY_MAP[len(VERBOSE_SEVERITY_MAP) - 1]

    init_logging(enabled=verbose_severity > 0,
                 level=verbose_level)


def init_logging(enabled=True, level=LoggingLevels.INFO):
    """ Initializes logging. """

    logging.basicConfig(level=level,
                        format="[%(levelname)s] %(asctime)s %(message)s",
                        datefmt='%d/%m/%y %H:%M:%S',
                        stream=sys.stdout)

    # logging.getLogger("Pyro4").setLevel(d)
    # logging.getLogger("Pyro4.core").setLevel(d)

    logging.addLevelName(LoggingLevels.TRACE, "TRACE")

    def trace(message, *args, **kws):
        if logging.getLogger().isEnabledFor(LoggingLevels.TRACE):
            logging.log(LoggingLevels.TRACE, message, *args, **kws)

    logging.trace = trace
    logging.Logger.trace = trace

    if not enabled:
        logging.disable()


e = logging.error
w = logging.warning
i = logging.info
d = logging.debug


# "Forward declaration"
def t(msg, *args, **kwargs):
    logging.trace(msg, *args, **kwargs)
