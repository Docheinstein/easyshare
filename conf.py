import logging
import os
import string
from pathlib import Path


class LoggingLevels:
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG
    TRACE = DEBUG - 1

class Conf:
    APP_NAME = "easyshare"
    APP_NAME_SERVER = "easyshare deamon"
    APP_NAME_CLIENT = "easyshare client"
    APP_NAME_SERVER_SHORT = "esd"
    APP_NAME_CLIENT_SHORT = "es"
    APP_VERSION = "0.1"
    DEFAULT_SERVER_DISCOVER_PORT = 12011
    DISCOVER_DEFAULT_TIMEOUT_SEC = 2
    DEFAULT_DEAMON_CONF_PATH = os.path.join(str(Path.home()), "fsd.conf")
    SERVER_NAME_ALPHABET = string.ascii_letters + "_-"
    SHARING_NAME_ALPHABET = string.ascii_letters + "_-"
