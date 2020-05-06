import os
import string

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.utils.colors import Color
from easyshare.utils.str import satisfy
from easyshare.utils.types import to_int

APP_NAME = "easyshare"
APP_NAME_SERVER = "easyshare deamon"
APP_NAME_CLIENT = "easyshare client"
APP_NAME_SERVER_SHORT = "esd"
APP_NAME_CLIENT_SHORT = "es"
APP_VERSION = "0.1"

DEFAULT_DISCOVER_PORT = 12019   # UDP
DEFAULT_SERVER_PORT =   12020   # TCP

SERVER_NAME_ALPHABET = string.ascii_letters + "_-"
SHARING_NAME_ALPHABET = string.ascii_letters + "_-."

AUTH_FMT = "{}${}${}"   # type$salt$hash

DIR_COLOR = Color.BLUE
# FILE_COLOR = Color.GREEN
FILE_COLOR = None

PROGRESS_COLOR = Color.BLUE
DONE_COLOR = Color.GREEN

ENV_EASYSHARE_VERBOSITY = "EASYSHARE_VERBOSITY"

ESD_PYRO_UID = "esd"

def esd_pyro_uri(addr: str, port: int):
    # e.g.  PYRO:esd@192.168.1.105:7777
    return "PYRO:{}@{}:{}".format(ESD_PYRO_UID, addr, port)

def is_sharing_name(s: str):
    return satisfy(s, SHARING_NAME_ALPHABET)


def is_server_name(s: str):
    return satisfy(s, SERVER_NAME_ALPHABET)


def easyshare_setup():
    # EASYSHARE_VERBOSITY
    starting_verbosity = os.environ.get(ENV_EASYSHARE_VERBOSITY)
    starting_verbosity = to_int(starting_verbosity,
                                raise_exceptions=False,
                                default=logging.VERBOSITY_NONE)

    root_log = get_logger(logging.ROOT_LOGGER_NAME)
    root_log.set_verbosity(starting_verbosity)
    root_log.d("Starting with verbosity = %d", starting_verbosity)