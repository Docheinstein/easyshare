import errno
import os
import shutil
from stat import S_ISDIR
from typing import Optional, List, Union, Tuple, Any, Callable


from easyshare.protocol.fileinfo import FileInfo, FileInfoTreeNode
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.shared.log import v, w, e
from easyshare.tree.tree import TreeRenderPostOrder
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.types import is_str, is_list

G = 1000000000
M = 1000000
K = 1000
UNITS = (1, K, M, G)

if os.name == 'nt':
    import win32api, win32con


def is_hidden(s: str):
    _, tail = os.path.split(s)

    if os.name == 'nt':
        attribute = win32api.GetFileAttributes(tail)
        return attribute & (win32con.FILE_ATTRIBUTE_HIDDEN | win32con.FILE_ATTRIBUTE_SYSTEM)
    else:
        return tail.startswith('.')


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
    return "0{}".format(prefixes[0])


def tree(path: str,
         sort_by: Union[str, List[str]] = "name",
         reverse=False,
         max_depth: int = None) -> Optional[FileInfoTreeNode]:
    if is_str(sort_by):
        sort_by = [sort_by]

    if not is_list(sort_by):
        return None

    sort_by_fields = list(filter(lambda sort_field: sort_field in ["name", "size", "ftype"], sort_by))
    print("TREE sorting by {}{}".format(sort_by, " (reverse)" if reverse else ""))

    f_stat = os.lstat(path)

    root = {
        "path": path,
        "name": ".",
        "ftype": FTYPE_DIR if S_ISDIR(f_stat.st_mode) else FTYPE_FILE,
        "size": f_stat.st_size,
    }

    cursor = root
    depth = 0

    try:
        while True:

            cur_path = cursor.get("path")
            cur_ftype = cursor.get("ftype")

            if cur_ftype == FTYPE_DIR and "children_unseen_info" not in cursor\
                    and (not max_depth or depth < max_depth):
                # Compute children, just the first time
                # print("Computing children of {}".format(cur_path))

                # It might fail (e.g. permission denied)
                try:
                    cursor["children_unseen_info"] = _ls(cur_path, sort_by_fields, reverse)
                except OSError:
                    w("Cannot descend %s", cur_path)
                    pass

            if not cursor.get("children_unseen_info"):
                # No unseen children, we have to go up

                is_root = True if not cursor.get("parent") else False

                ex_cursor = cursor

                # Go up to the parent, nothing to do here
                if not is_root:
                    # print("Going ^ to {} ", cursor.get("parent").get("path"))
                    cursor = cursor.get("parent")
                    depth -= 1

                # print("Cleaning up node")
                ex_cursor.pop("parent", None)
                ex_cursor.pop("children_unseen_info", None)
                ex_cursor.pop("path", None)

                if is_root:
                    # print("done")
                    break

                continue

            # There is a children unseen, take out
            unseen_child_info = cursor.get("children_unseen_info").pop(0)
            # print("Took out unseen child", unseen_child_info.get("name"))

            # Add it to the children
            cursor.setdefault("children", [])

            child = dict(
                unseen_child_info,
                parent=cursor,
                path=os.path.join(cur_path, unseen_child_info.get("name"))
            )

            # print("Adding child to children", child)

            cursor.get("children").append(child)

            # Go down
            cursor = child
            depth += 1

    except Exception as ex:
        e("LS execution exception %s", ex)
        return None

    return root


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


def _ls(path: str, sort_by_fields: List[str], reverse=False) -> Optional[List[FileInfo]]:
    ret: List[FileInfo] = []

    if os.path.isfile(path):
        f_stat = os.lstat(os.path.join(path))
        _, tail = os.path.split(path)
        return [{
            "name": tail,
            "ftype": FTYPE_FILE,
            "size": f_stat.st_size
        }]

    if not os.path.isdir(path):

        e("Cannot perform ls; invalid path")
        return None

    # Take the other info (size, filetype, ...)
    for f in os.listdir(path):
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


def mv(src: str, dest: str) -> bool:
    try:
        shutil.move(src, dest)
        return True
    except Exception as ex:
        e("MV exception %s", ex)
        raise ex


def cp(src: str, dest: str) -> bool:
    try:
        shutil.copy2(src, dest, follow_symlinks=False)
        return True
    except Exception as ex:
        e("CP exception %s", ex)
        raise ex


if __name__ == "__main__":
    root = tree("/home/stefano/Temp/test_cartaceo")
    print(json_to_pretty_str(root))

    for prefix, node, _ in TreeRenderPostOrder(root):
        print("{}{}".format(prefix, node.get("name")))
