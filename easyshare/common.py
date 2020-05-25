import os
import string

from easyshare import logging
from easyshare.consts import ansi
from easyshare.logging import get_logger, init_logging
from easyshare.styling import enable_colors
from easyshare.utils.env import are_colors_supported
from easyshare.utils.str import satisfychars
from easyshare.utils.types import to_int


# =====================
# === APP META DATA ===
# =====================

APP_NAME = "easyshare"
APP_NAME_SERVER = "esd"
APP_NAME_CLIENT = "es"
APP_VERSION = "0.2"

APP_INFO = f"{APP_NAME} {APP_VERSION}"

# =====================
# ===== RESOURCES =====
# =====================

EASYSHARE_RESOURCES_PKG = "easyshare.res"


# =====================
# ======= COLORS ======
# =====================

DIR_COLOR = ansi.FG_BLUE
FILE_COLOR = None

PROGRESS_COLOR = ansi.FG_BLUE
SUCCESS_COLOR = ansi.FG_GREEN
ERROR_COLOR = ansi.FG_RED


# =====================
# ==== ENVIRONMENT ====
# =====================

ENV_EASYSHARE_VERBOSITY = "EASYSHARE_VERBOSITY"


# =====================
# ==== RAW NETWORK ====
# =====================

DEFAULT_DISCOVER_PORT = 12019   # UDP
DEFAULT_SERVER_PORT =   12020   # TCP

DEFAULT_DISCOVER_TIMEOUT = 2    # sec

# TODO: tests for figure out what's the best buffer size
BEST_BUFFER_SIZE = 4096


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
    return satisfychars(s, SHARING_NAME_ALPHABET)


def is_server_name(s: str):
    return satisfychars(s, SERVER_NAME_ALPHABET)


# =====================
# ======== SETUP ======
# =====================

def easyshare_setup():
    """
    Configures easyshare: initializes the colors and the logging.
    """
    # disable colors when redirection is involved or if
    # colors are disabled
    colors_disabled = os.getenv('ANSI_COLORS_DISABLED')
    enable_colors(are_colors_supported() and not colors_disabled)

    # Init logging manually now, after enable_colors call
    init_logging()

    # EASYSHARE_VERBOSITY
    starting_verbosity = os.environ.get(ENV_EASYSHARE_VERBOSITY)
    starting_verbosity = to_int(starting_verbosity,
                                raise_exceptions=False,
                                default=logging.VERBOSITY_NONE)

    root_log = get_logger()
    root_log.set_verbosity(starting_verbosity)
    root_log.d("Starting with verbosity = %d", starting_verbosity)
