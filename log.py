import logging
import sys

from conf import LoggingLevels


def init_logging(enabled=True, level=LoggingLevels.INFO):
    """ Initializes logging. """

    logging.basicConfig(level=level,
                        format="[%(levelname)s] %(asctime)s %(message)s",
                        datefmt='%d/%m/%y %H:%M:%S',
                        stream=sys.stdout)

    # logging.getLogger("Pyro4").setLevel(logging.DEBUG)
    # logging.getLogger("Pyro4.core").setLevel(logging.DEBUG)

    logging.addLevelName(LoggingLevels.TRACE, "TRACE")

    def trace(message, *args, **kws):
        if logging.getLogger().isEnabledFor(LoggingLevels.TRACE):
            logging.log(LoggingLevels.TRACE, message, *args, **kws)

    logging.trace = trace
    logging.Logger.trace = trace

    if not enabled:
        logging.disable()

