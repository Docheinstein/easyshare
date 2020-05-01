import errno
import fcntl
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from stat import S_ISDIR
from typing import Optional, List, Union, Tuple, Any, Callable

from easyshare.logging import get_logger
from easyshare.protocol.fileinfo import FileInfo, FileInfoTreeNode
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.tree.tree import TreeRenderPostOrder
from easyshare.utils.colors import red
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.types import is_str, is_list, bytes_to_str

log = get_logger(__name__)

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
    s = pathify(s)
    return not s.startswith(os.sep)


def is_abspath(s: str) -> bool:
    s = pathify(s)
    return s.startswith(os.sep)


def relpath(s: str) -> str:
    s = pathify(s)
    return s.lstrip(os.sep)


def abspath(s: str) -> str:
    s = pathify(s)
    return s if is_abspath(s) else (os.sep + s)


def pathify(s: str) -> str:
    return os.path.expanduser(s)


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
         reverse: bool = False,
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
                    log.w("Cannot descend %s", cur_path)
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
        log.e("LS execution exception %s", ex)
        return None

    return root


def ls(path: str, sort_by: Union[str, List[str]] = "name", reverse=False) -> Optional[List[FileInfo]]:
    if is_str(sort_by):
        sort_by = [sort_by]

    if not is_list(sort_by):
        return None

    sort_by_fields = list(filter(lambda sort_field: sort_field in ["name", "size", "ftype"], sort_by))
    log.i("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    try:
        return _ls(path, sort_by_fields, reverse)
    except Exception as ex:
        log.e("LS execution exception %s", ex)
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
        log.e("Cannot perform ls; invalid path")
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

                log.e("RM error occurred on path '%s': %s",
                  error_path,
                  excinfo_error)

                if error_callback:  # should be defined
                    error_callback(excinfo_error)

            ignore_errors = True if error_callback else False
            shutil.rmtree(path, ignore_errors=ignore_errors, onerror=handle_rmtree_error)
            return True

        log.e("Cannot delete; not file nor dir '%s'", path)

        # Manually notify a file not found exception
        if error_callback:
            error_callback(FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), path
            ))
        return False
    except Exception as ex:
        # Notify the exception of a valid action (could be permission denied, ...)
        log.e("RM execution exception %s", ex)
        if error_callback:
            error_callback(ex)
        return False


def mv(src: str, dest: str) -> bool:
    try:
        shutil.move(src, dest)
        return True
    except Exception as ex:
        log.e("MV exception %s", ex)
        raise ex


def cp(src: str, dest: str) -> bool:
    try:
        if os.path.isdir(src) and os.path.isdir(dest):
            log.d("Recursive copy DIR => DIR detected")
            srchead, srctail = os.path.split(src)
            dest = os.path.join(dest, srctail)
            log.d("Definitive src = '%s' | dst = '%s'", src, dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest, follow_symlinks=False)
        return True
    except Exception as ex:
        log.e("CP exception %s", ex)
        raise ex


def run_attached(cmd: str, stderr_redirect: int = None):
    proc = subprocess.Popen(cmd, shell=True, text=True, stderr=stderr_redirect)
    proc.wait()
    return proc.returncode
#
#
# def run_detached(cmd: str,
#                  stdout_hook: Callable[[str], None],
#                  end_hook: Callable[[int], None]):
#
#
#     def proc_handler(proc: subprocess.Popen):
#         while proc.poll() is None:
#             # print("stdout select()")
#             # rlist, wlist, xlist = select.select([proc.stdout], [], [], 0.04)
#             # print("stdout select() end")
#
#             # if proc.stdout in rlist:
#             #     line = proc.stdout.read()
#             #     stdout_hook(line)
#
#             for line in proc.stdout:
#                 stdout_hook(line)
#
#             # print("@ WAIT on select()")
#             # rlist, wlist, xlist = select.select([sys.stdin, proc.stdout], [], [])
#             #
#             # print("@ R: {} | W: {}".format(rlist, wlist))
#             #
#             # if rlist:
#             #     for stream in rlist:
#             #         # if stream == sys.stdin:
#             #         #     for line in sys.stdin:
#             #         #         print("< ", line, end="")
#             #         #         proc.stdin.write(line)
#             #         #         proc.stdin.flush()
#             #         if stream == proc.stdout:
#             #             for line in proc.stdout:
#             #                 stdout_hook(line)
#             # else:
#             #     print("--- nothing to read ---")
#
#         # print("@ END ({})".format(proc.returncode))
#         end_hook(proc.returncode)
#
#
#     proc = subprocess.Popen(cmd, shell=True, text=True,
#                             stdout=subprocess.PIPE,
#                             stderr=subprocess.STDOUT,
#                             stdin=subprocess.PIPE)
#
#
#     stdout_flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
#
#     # p("changing stdout mode => non blocking")
#     fcntl.fcntl(proc.stdout, fcntl.F_SETFL, stdout_flags | os.O_NONBLOCK)
#
#     handler_thread = threading.Thread(target=proc_handler, daemon=True, args=(proc, ))
#     handler_thread.start()
#
#     return proc, handler_thread
#


def run_detached(cmd: str,
                 stdout_hook: Callable[[str], None],
                 end_hook: Callable[[int], None]):

    def proc_handler(proc: subprocess.Popen):
        flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        while proc.poll() is None:
            rlist, wlist, xlist = select.select([proc.stdout], [], [], 0.04)

            if proc.stdout in rlist:
                line = proc.stdout.read()
                if line:
                    if stdout_hook:
                        stdout_hook(line)

        end_hook(proc.returncode)

        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags)

    popen_proc = subprocess.Popen(cmd, shell=True, text=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,
                                  stdin=subprocess.PIPE)

    proc_handler = threading.Thread(target=proc_handler, daemon=True, args=(popen_proc, ))
    proc_handler.start()

    return popen_proc, proc_handler


#
# def stdin_read_nonblocking(continue_condition: Callable[..., bool],
#                            stdin_hook: Callable[[str], None],
#                            eof_hook: Callable):
#     flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
#     fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
#
#     # try:
#     while continue_condition():
#         rlist, wlist, xlist = select.select([sys.stdin], [], [], 0.04)
#
#         if sys.stdin in rlist:
#             line_b = sys.stdin.buffer.read()
#
#             if line_b:
#                 if stdin_hook:
#                     stdin_hook(bytes_to_str(line_b))
#             else:
#                 if eof_hook:
#                     eof_hook()
#     # except KeyboardInterrupt:
#     #     print("\nCTRL+C")
#     # except EOFError:
#     #     print("\nCTRL+D")
#
#     fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags)
#

if __name__ == "__main__":
    pass