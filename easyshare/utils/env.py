import os
import shutil
import sys
from stat import S_ISCHR
from typing import Tuple

from easyshare.logging import get_logger


log = get_logger(__name__)

_UNIX = os.name == "posix"
_WIN = os.name == "nt"


def is_unix():
    return _UNIX


def is_windows():
    return _WIN


def is_terminal(fileno: int) -> bool:
    """ Returns true if the given file number belongs to a terminal (stdout)"""
    return S_ISCHR(os.fstat(fileno).st_mode)


def is_stdout_terminal() -> bool:
    """ Returns true if stdout belongs to a terminal """
    return is_terminal(sys.stdout.fileno())


def are_colors_supported() -> bool:
    """
    Returns true if colors are supported (actually only if
    stdout is bound to a terminal)
    """
    return is_stdout_terminal()


def terminal_size(fallback=(80, 24)) -> Tuple[int, int]:
    """ Returns the terminal size, or the fallback if it can't be retrieved"""
    try:
        columns, rows = shutil.get_terminal_size(fallback=fallback)
    except:
        log.w("Failed to retrieved terminal size, using fallback")
        return fallback
    return columns, rows


def is_unicode_supported(stream=sys.stdout) -> bool:
    """ Returns true if the given stream supports unicode"""
    encoding = stream.encoding

    # Attempts to encode a character and see what happens
    try:
        '\u2588'.encode(stream.encoding)
        return True
    except UnicodeEncodeError:
        return False
    except Exception:
        try:
            return encoding.lower().startswith("utf-") or encoding == "U8"
        except:
            return False