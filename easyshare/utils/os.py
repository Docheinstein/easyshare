import errno
import os
import shutil
import sys
from stat import S_ISDIR
from typing import Optional, List, Union, Tuple, Any, Callable

import anytree
from anytree import RenderTree, AnyNode, AbstractStyle, ContStyle, ContRoundStyle

from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.shared.log import v, w, e
from easyshare.utils.json import json_to_pretty_str, json_to_str
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


def tree(path: str, sort_by: Union[str, List[str]] = "name", reverse=False) -> Optional[AnyNode]:
    ret: List[FileInfo] = []

    if is_str(sort_by):
        sort_by = [sort_by]

    if not is_list(sort_by):
        return None

    sort_by_fields = list(filter(lambda sort_field: sort_field in ["name", "size", "ftype"], sort_by))
    print("TREE sorting by {}{}".format(sort_by, " (reverse)" if reverse else ""))

    f_stat = os.lstat(path)

    tree_root = AnyNode(
        fpath=path,
        finfo={
            "name": ".",
            "ftype": FTYPE_DIR if S_ISDIR(f_stat.st_mode) else FTYPE_FILE,
            "size": f_stat.st_size
        },
        nexts=_ls(path, sort_by_fields, reverse)
    )

    cur_ref = tree_root

    try:
        while True:

            cur_path = cur_ref.fpath
            # print("cur_path |", cur_path)

            # Check whether the current node has valid nexts
            # (It has nexsts only if it is a dir and has something inside it)
            if not getattr(cur_ref, "nexts", None):
                # No next, go upward or quit if we are on the root
                if cur_ref.parent:
                    cur_ref = cur_ref.parent
                    # print("went upwardto ", cur_ref.finfo.get("name"))
                    continue
                else:
                    # print("done")
                    break

            # Treating a directory with something inside

            # Get the next finfo (from the beginning)
            next_finfo = cur_ref.nexts.pop(0)
            next_fname = next_finfo.get("name")
            next_ftype = next_finfo.get("ftype")
            next_path = os.path.join(cur_path, next_fname)

            # print("Taken out finfo '{}'".format(json_to_str(next_finfo)))

            # Add the node
            ex_cur_ref = cur_ref

            cur_ref = AnyNode(
                parent=ex_cur_ref,
                fpath=next_path,
                finfo=next_finfo
            )

            # print("Linked {} -> {}".format(ex_cur_ref.fpath, cur_ref.fpath))

            if next_ftype != FTYPE_DIR:
                # Nothing else to do here
                continue

            # We have to compute the nexts for this dir and sort using
            # the given parameters

            cur_ref.nexts = _ls(next_path, sort_by_fields, reverse)

            # print("Computed next of {} = {}".format(cur_ref.fpath, cur_ref.nexts))


    except Exception as ex:
        # print("TREE execution exception %s" % ex)
        return None

    return tree_root


def ls(path: str, sort_by: Union[str, List[str]] = "name", reverse=False) -> Optional[List[FileInfo]]:
    if is_str(sort_by):
        sort_by = [sort_by]

    if not is_list(sort_by):
        return None

    sort_by_fields = list(filter(lambda sort_field: sort_field in ["name", "size", "ftype"], sort_by))
    v("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    try:
        return _ls(path, sort_by_fields, reverse)
    except Exception as ex:
        e("LS execution exception %s", ex)
        return None


def _ls(path: str, sort_by_fields: List[str], reverse=False) -> List[FileInfo]:
    ret: List[FileInfo] = []

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

    if reverse:
        ret.reverse()

    return ret


def rm(path: str, error_callback: Callable[[Exception], None] = None) -> bool:
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True

        if os.path.isdir(path):
            def handle_rmtree_error(error_func,
                                    error_path,
                                    error_excinfo: Tuple[Any, Exception, Any]):

                excinfo_class, excinfo_error, excinfo_traceback = error_excinfo

                e("RM error occurred on path '%s': %s",
                  error_path,
                  excinfo_error)

                if error_callback:  # should be defined
                    error_callback(excinfo_error)

            ignore_errors = True if error_callback else False
            shutil.rmtree(path, ignore_errors=ignore_errors, onerror=handle_rmtree_error)
            return True

        e("Cannot delete; not file nor dir '%s'", path)

        # Manually notify a file not found exception
        if error_callback:
            error_callback(FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), path
            ))
        return False
    except Exception as ex:
        # Notify the exception of a valid action (could be permission denied, ...)
        e("RM execution exception %s", ex)
        if error_callback:
            error_callback(ex)
        return False


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


if __name__ == "__main__":
    for pre, fill, node in RenderTree(
            tree("/home/stefano/Temp/treetest",
                reverse=False,
                sort_by=["name", "ftype"]
            ),
            style=ContRoundStyle):
        # print(node)
        print("%s%s" % (pre, node.finfo.get("name")))
