import os
import string

from easyshare import logging
from easyshare.consts import ansi
from easyshare.logging import get_logger, init_logging
from easyshare.styling import enable_colors
from easyshare.utils.env import is_stdout_terminal
from easyshare.utils.str import satisfy
from easyshare.utils.types import to_int


# =====================
# === APP META DATA ===
# =====================

APP_NAME = "easyshare"
APP_NAME_SERVER = "easyshare deamon"
APP_NAME_CLIENT = "easyshare es"
APP_NAME_SERVER_SHORT = "esd"
APP_NAME_CLIENT_SHORT = "es"
APP_VERSION = "0.1"

APP_INFO = "{} {}".format(APP_NAME, APP_VERSION)

# =====================
# ===== RESOURCES =====
# =====================

RESOURCES_PKG = "easyshare.res"


# =====================
# ======= COLORS ======
# =====================

DIR_COLOR = ansi.FG_BLUE
FILE_COLOR = None

PROGRESS_COLOR = ansi.FG_BLUE
DONE_COLOR = ansi.FG_GREEN


# =====================
# ==== ENVIRONMENT ====
# =====================

ENV_EASYSHARE_VERBOSITY = "EASYSHARE_VERBOSITY"


# =====================
# ==== RAW NETWORK ====
# =====================

DEFAULT_DISCOVER_PORT = 12019   # UDP
DEFAULT_SERVER_PORT =   12020   # TCP

def transfer_port(server_port: int):
    return server_port + 1


# =====================
# ==== PYRO NETWORK ====
# =====================

ESD_PYRO_UID = "esd"


# =====================
# === SHARING/SERVER ==
# =====================

SERVER_NAME_ALPHABET = string.ascii_letters + "_-"
SHARING_NAME_ALPHABET = string.ascii_letters + "_-."

def is_sharing_name(s: str):
    return satisfy(s, SHARING_NAME_ALPHABET)


def is_server_name(s: str):
    return satisfy(s, SERVER_NAME_ALPHABET)


# =====================
# ======== SETUP ======
# =====================

def easyshare_setup():
    # disable colors when redirection is involved or if
    # colors are disabled
    colors_disabled = os.getenv('ANSI_COLORS_DISABLED')
    enable_colors(not colors_disabled and is_stdout_terminal())

    # EASYSHARE_VERBOSITY
    starting_verbosity = os.environ.get(ENV_EASYSHARE_VERBOSITY)
    starting_verbosity = to_int(starting_verbosity,
                                raise_exceptions=False,
                                default=logging.VERBOSITY_NONE)

    root_log = get_logger(logging.ROOT_LOGGER_NAME)
    root_log.set_verbosity(starting_verbosity)
    root_log.d("Starting with verbosity = %d", starting_verbosity)
