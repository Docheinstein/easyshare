import enum
import os
import string

from easyshare.consts import ansi
from easyshare.utils.env import is_styling_supported
from easyshare.utils.str import satisfychars
from easyshare.utils.types import to_int


# =====================
# === APP META DATA ===
# =====================

APP_NAME = "easyshare"
APP_NAME_SERVER = "esd"
APP_NAME_CLIENT = "es"
APP_VERSION = "0.14"

APP_INFO = f"{APP_NAME} {APP_VERSION}"

# =====================
# ===== RESOURCES =====
# =====================

EASYSHARE_RESOURCES_PKG = "easyshare.res"
EASYSHARE_ES_CONF = ".esrc"
EASYSHARE_HISTORY = ".es_history"


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

ENV_ANSI_COLORS_DISABLED = "ANSI_COLORS_DISABLED"
ENV_EASYSHARE_VERBOSITY = "EASYSHARE_VERBOSITY"


# =====================
# ==== RAW NETWORK ====
# =====================

DEFAULT_DISCOVER_PORT = 12019   # UDP
DEFAULT_SERVER_PORT =   12020   # TCP

DEFAULT_DISCOVER_WAIT = 2            # sec
DEFAULT_TRANSFER_SOCKET_TIMEOUT = 120   # sec

BEST_BUFFER_SIZE = 4096

# =====================
# ====== TRACING ======
# =====================

TRACING_NONE = 0
TRACING_TEXT = 1
TRACING_BIN = 2

TRACING_MIN = 0
TRACING_MAX = TRACING_BIN

# =====================
# ===== VERBOSITY =====
# =====================

VERBOSITY_NONE = 0
VERBOSITY_ERROR = 1
VERBOSITY_WARNING = 2
VERBOSITY_INFO = 3
VERBOSITY_DEBUG = 4
VERBOSITY_HUGE = 5

VERBOSITY_MIN = VERBOSITY_NONE
VERBOSITY_MAX = VERBOSITY_HUGE
VERBOSITY_DEFAULT = VERBOSITY_INFO

class TransferProtocol(enum.Enum):
    TCP = "TCP"
    UDP = "UDP"


class TransferDirection(enum.Enum):
    IN = "IN"
    OUT = "OUT"


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

easyshare_setup_done = False

def easyshare_setup(default_verbosity: int = VERBOSITY_NONE):
    """
    Configures easyshare: initializes the colors and the logging.
    """

    global easyshare_setup_done
    if easyshare_setup_done:
        return
    easyshare_setup_done = True

    from easyshare.styling import init_styling
    from easyshare.settings import set_setting, Settings

    # disable colors when redirection is involved or if colors are disabled
    env_ansi_disabled = os.getenv(ENV_ANSI_COLORS_DISABLED)
    env_starting_verbosity = os.getenv(ENV_EASYSHARE_VERBOSITY)

    init_styling()
    set_setting(Settings.COLORS, is_styling_supported() and not env_ansi_disabled)

    # Init logging manually now, after enable_colors call
    starting_verbosity = to_int(env_starting_verbosity,
                                raise_exceptions=False,
                                default=default_verbosity)

    set_setting(Settings.VERBOSITY, starting_verbosity)