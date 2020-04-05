import os
from stat import S_ISDIR
from typing import Optional, List

from easyshare.protocol.fileinfo import FileInfo

G = 1000000000
M = 1000000
K = 1000


def size_str(size: int, fmt="{:0.1f}{}", identifiers=(" ", "K", "M", "G")):
    if size > G:
        return fmt.format(size / G, identifiers[3])
    if size > M:
        return fmt.format(size / M, identifiers[2])
    if size > K:
        return fmt.format(size / K, identifiers[1])
    return fmt.format(size, identifiers[0])


def ls(path: str, sort_by="name") -> Optional[List[FileInfo]]:
    ret: List[FileInfo] = []

    if sort_by not in ["name", "size", "type"]:
        sort_by = "name"

    try:
        ls_result = os.listdir(path)

        # Take the other info (size, filetype, ...)
        for f in ls_result:
            f_stat = os.lstat(os.path.join(path, f))

            ret.append({
                "name": f,
                "size": f_stat.st_size,
                "type": "dir" if S_ISDIR(f_stat.st_mode) else "file"
            })

        # Sort the results
        ret = sorted(ret, key=lambda fi: fi[sort_by])

    except Exception:
        pass

    return ret