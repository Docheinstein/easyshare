import os
import shutil
import sys
from stat import S_ISDIR
from typing import Optional, List, Union, Tuple

from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.shared.log import v, w
from easyshare.utils.types import is_str, is_list

G = 1000000000
M = 1000000
K = 1000
UNITS = (1, K, M, G)


def is_relpath(s: str) -> bool:
    return not s.startswith(os.sep)


def is_abspath(s: str) -> bool:
    return s.startswith(os.sep)


def relpath(s: str) -> str:
    return s.lstrip(os.sep)


def abspath(s: str) -> str:
    return s if is_abspath(s) else (os.sep + s)


def size_str(size: float,
             prefixes=(" ", "K", "M", "G"),
             precisions=(0, 0, 1, 1)) -> str:
    i = len(UNITS) - 1
    while i >= 0:
        u = UNITS[i]
        if size > u:
            return ("{:0." + str(precisions[i]) + "f}{}").format(size / u, prefixes[i])
        i -= 1
    return "0"


def ls(path: str, sort_by: Union[str, List[str]] = "name", reverse=False) -> Optional[List[FileInfo]]:
    ret: List[FileInfo] = []

    if is_str(sort_by):
        sort_by = [sort_by]

    if not is_list(sort_by):
        return None

    sort_by_fields = filter(lambda sort_field: sort_field in ["name", "size", "ftype"], sort_by)
    v("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    try:
        ls_result = os.listdir(path)

        # Take the other info (size, filetype, ...)
        for f in ls_result:
            f_stat = os.lstat(os.path.join(path, f))
            ret.append({
                "name": f,
                "ftype": FTYPE_DIR if S_ISDIR(f_stat.st_mode) else FTYPE_FILE,
                "size": f_stat.st_size,
            })

        # Sort the result for each field of sort_by
        for sort_field in sort_by_fields:
            ret = sorted(ret, key=lambda fi: fi[sort_field])

    except Exception as ex:
        w("LS execution exception %s", ex)
        return None

    if reverse:
        ret.reverse()
        return ret

    return ret


def terminal_size(fallback=(80, 24)) -> Tuple[int, int]:
    try:
        columns, rows = shutil.get_terminal_size(fallback=fallback)
    except:
        w("Failed to retrieved terminal size, using fallback")
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