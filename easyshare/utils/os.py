import os
from stat import S_ISDIR
from typing import Optional, List, Union

from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.shared.log import v, w
from easyshare.utils.types import is_str, is_list

G = 1000000000
M = 1000000
K = 1000


def is_relpath(s: str) -> bool:
    return not s.startswith(os.sep)


def is_abspath(s: str) -> bool:
    return s.startswith(os.sep)


def relpath(s: str) -> str:
    return s.lstrip(os.sep)


def abspath(s: str) -> str:
    return s if is_abspath(s) else (os.sep + s)


def size_str(size: int, fmt="{:0.1f}{}", identifiers=(" ", "K", "M", "G")):
    if size > G:
        return fmt.format(size / G, identifiers[3])
    if size > M:
        return fmt.format(size / M, identifiers[2])
    if size > K:
        return fmt.format(size / K, identifiers[1])
    return fmt.format(size, identifiers[0])


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
                "size": f_stat.st_size
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
