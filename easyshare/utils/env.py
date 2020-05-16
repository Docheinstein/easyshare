import os
import shutil
import sys
from stat import S_ISCHR
from typing import Tuple

from easyshare.logging import get_logger


log = get_logger(__name__)


def is_terminal(fileno: int):
    return S_ISCHR(os.fstat(fileno).st_mode)


def is_stdout_terminal():
    return is_terminal(sys.stdout.fileno())

def are_colors_supported():
    return is_stdout_terminal()

def terminal_size(fallback=(80, 24)) -> Tuple[int, int]:
    try:
        columns, rows = shutil.get_terminal_size(fallback=fallback)
    except:
        log.w("Failed to retrieved terminal size, using fallback")
        return fallback
    return columns, rows


def is_unicode_supported(stream=sys.stdout) -> bool:
    encoding = stream.encoding

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


if __name__ == "__main__":
    print(terminal_size())