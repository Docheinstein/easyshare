import string

from easyshare.utils.colors import Color
from easyshare.utils.str import satisfy

APP_NAME = "easyshare"
APP_NAME_SERVER = "easyshare deamon"
APP_NAME_CLIENT = "easyshare client"
APP_NAME_SERVER_SHORT = "esd"
APP_NAME_CLIENT_SHORT = "es"
APP_VERSION = "0.1"

DEFAULT_DISCOVER_PORT = 12011

SERVER_NAME_ALPHABET = string.ascii_letters + "_-"
SHARING_NAME_ALPHABET = string.ascii_letters + "_-."

AUTH_FMT = "{}${}${}"   # type$salt$hash

DIR_COLOR = Color.BLUE
# FILE_COLOR = Color.GREEN
FILE_COLOR = None

PROGRESS_COLOR = Color.BLUE
DONE_COLOR = Color.GREEN

ENV_EASYSHARE_VERBOSITY = "EASYSHARE_VERBOSITY"

def is_sharing_name(s: str):
    return satisfy(s, SHARING_NAME_ALPHABET)


def is_server_name(s: str):
    return satisfy(s, SERVER_NAME_ALPHABET)

