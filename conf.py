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
    APP_VERSION = "0.1"
    DISCOVER_PORT_SERVER = 12011
    DISCOVER_PORT_CLIENT = 12021
    DISCOVER_DEFAULT_TIMEOUT_SEC = 2
    DEFAULT_DEAMON_CONF_PATH = os.path.join(str(Path.home()), "fsd.conf")
    SHARING_NAME_ALPHABET = string.ascii_letters + "_"
