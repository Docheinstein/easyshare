from easyshare import logging
from easyshare.logging import get_logger


def enable_pyro_logging(enabled: bool = True):
    pyro_log = get_logger("Pyro5", force_initialize=enabled)
    pyro_log.set_verbosity(logging.VERBOSITY_MAX if enabled else logging.VERBOSITY_MIN)

def is_pyro_logging_enabled() -> bool:
    pyro_log = get_logger("Pyro5")
    return pyro_log.verbosity == logging.VERBOSITY_MAX


def pyro_uri(uid: str, addr: str, port: int):
    # e.g.  PYRO:esd@192.168.1.105:7777
    return "PYRO:{}@{}:{}".format(uid, addr, port)