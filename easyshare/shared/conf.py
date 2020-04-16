import string

APP_NAME = "easyshare"
APP_NAME_SERVER = "easyshare deamon"
APP_NAME_CLIENT = "easyshare client"
APP_NAME_SERVER_SHORT = "esd"
APP_NAME_CLIENT_SHORT = "es"
APP_VERSION = "0.1"

DEFAULT_DISCOVER_PORT = 12011

SERVER_NAME_ALPHABET = string.ascii_letters + "_-"
SHARING_NAME_ALPHABET = string.ascii_letters + "_-"

AUTH_FMT = "{}${}${}"   # type$salt$hash
