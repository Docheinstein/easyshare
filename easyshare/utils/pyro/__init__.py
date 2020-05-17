from easyshare import logging
from easyshare.logging import get_logger


def enable_pyro_logging(enabled: bool = True):
    """ Enables or disable the pyro logger """
    # force_initialize is needed for add the easyshare
    # extension to the Pyro Logger (i.e. verbosity)
    pyro_log = get_logger("Pyro5", force_initialize=enabled)
    pyro_log.set_verbosity(logging.VERBOSITY_MAX if enabled else logging.VERBOSITY_MIN)

def is_pyro_logging_enabled() -> bool:
    """ Returns whether the pyro logger is enabled """
    pyro_log = get_logger("Pyro5")
    return pyro_log.verbosity == logging.VERBOSITY_MAX


def pyro_uri(uid: str, addr: str, port: int):
    """ Build a pyro URI of the form PYRO:<uid>:<addr>:<port>"""
    return f"PYRO:{uid}@{addr}:{port}"