import shutil
import sys
from typing import Tuple



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
