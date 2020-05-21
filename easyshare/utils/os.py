import errno
import fcntl
import os
import select
import shutil
import subprocess
import threading
from pathlib import Path
from stat import S_ISDIR
from typing import Optional, List, Union, Tuple, Any, Callable

from easyshare.logging import get_logger
from easyshare.protocol.types import FTYPE_FILE, FTYPE_DIR, FileInfoTreeNode, FileInfo, create_file_info
from easyshare.utils.types import is_str, is_list, list_wrap

log = get_logger(__name__)


def is_windows():
    return os.name == "nt"


def is_unix():
    return os.name == "posix"


if is_windows():
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


# def pathify(s: str) -> str:
#     return os.path.expanduser(s)


def LocalPath(p: Optional[str] = None, default="") -> Path:
    return Path(p or default).expanduser()

# def parent_dir(p: Path):
#     # os.path.split() differs from pathlib.parent
#     # pathlib.parent of /home/user/ is "/home"
#     # os.path.split of /home/user/ is ("/home/user/", "")
#     return p if str(p).endswith(os.path.sep) else p.parent


def tree(path: Path,
         sort_by: Union[str, List[str]] = "name",
         reverse: bool = False,
         max_depth: int = None) -> Optional[FileInfoTreeNode]:
    if not path:
        raise TypeError("Path should be valid")

    sort_by = list(filter(lambda field: field in ["name", "size", "ftype"],
                          list_wrap(sort_by)))

    log.i("TREE sorting by {}{}".format(sort_by, " (reverse)" if reverse else ""))

    root = create_file_info(path)
    # root["path"] = str(path)
    root["path"] = path

    cursor = root
    depth = 0

    while True:
        cur_path: Path = cursor.get("path")
        cur_ftype: FileInfo = cursor.get("ftype")

        if cur_ftype == FTYPE_DIR and "children_unseen_info" not in cursor\
                and (not max_depth or depth < max_depth):
            # Compute children, just the first time
            # print("Computing children of {}".format(cur_path))

            # It might fail (e.g. permission denied)
            try:
                cursor["children_unseen_info"] = ls(cur_path,
                                                    sort_by=sort_by,
                                                    reverse=reverse)
            except OSError:
                log.w("Cannot descend %s", cur_path)
                pass

        # Check whether we have child of this node this visit.
        # If we have nothing to see down, we have to go up until
        # we have children to visit (or we reach the root and therefore
        # the traversal is finished)
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
            # Cleanup the node from the non 'FileInfo' stuff
            ex_cursor.pop("parent", None)
            ex_cursor.pop("children_unseen_info", None)
            ex_cursor.pop("path", None)

            if is_root:
                # Finished all the traversal
                break

            continue

        # There is an unseen children, take it out
        unseen_child_info = cursor.get("children_unseen_info").pop(0)
        # print("Took out unseen child", unseen_child_info.get("name"))

        # Add it to the children
        cursor.setdefault("children", [])

        child = dict(
            unseen_child_info,
            parent=cursor,
            path=cur_path.joinpath(unseen_child_info.get("name"))
            # path=os.path.join(cur_path, unseen_child_info.get("name"))
            # path=os.path.join(cur_path, unseen_child_info.get("name"))
        )

        # print("Adding child to children", child)

        cursor.get("children").append(child)

        # Go down
        cursor = child
        depth += 1

    return root


# def ls(path: Path, sort_by: Union[str, List[str]] = "name", reverse=False) -> Optional[List[FileInfo]]:
    # sort_by = list(filter(lambda sort_field: sort_field in ["name", "size", "ftype"],
    #                       list_wrap(sort_by)))
    #
    # log.i("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    # try:
    #     return _ls(path, sort_by, reverse)
    # except Exception as ex:
    #     log.e("LS execution exception %s", ex)
    #     return None


def ls(path: Path,
       sort_by: Union[str, List[str]] = "name",
       reverse: bool = False) -> Optional[List[FileInfo]]:
    if not path:
        raise TypeError("Path should be valid")

    sort_by = list(filter(lambda field: field in ["name", "size", "ftype"],
                          list_wrap(sort_by)))

    log.i("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    ret: List[FileInfo] = []

    # Single file
    if path.is_file():
        return [create_file_info(path)]

    if not path.is_dir():
        log.e("Cannot perform ls; invalid path")
        raise FileNotFoundError()

    # Directory
    for p in path.iterdir():
        ret.append(create_file_info(p))

    # Sort the result for each field of sort_by
    for sort_field in sort_by:
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


def run_detached(cmd: str,
                 stdout_hook: Callable[[str], None],
                 stderr_hook: Callable[[str], None],
                 end_hook: Callable[[int], None]):

    def proc_handler(proc: subprocess.Popen):
        flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        while proc.poll() is None:
            rlist, wlist, xlist = select.select([proc.stdout, proc.stderr], [], [], 0.04)

            if proc.stdout in rlist:
                line = proc.stdout.read()
                if line:
                    if stdout_hook:
                        stdout_hook(line)
            elif proc.stderr in rlist:
                line = proc.stderr.read()
                if line:
                    if stderr_hook:
                        stderr_hook(line)

        end_hook(proc.returncode)

        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags)

    popen_proc = subprocess.Popen(cmd, shell=True, text=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  stdin=subprocess.PIPE)

    proc_handler = threading.Thread(target=proc_handler, daemon=True, args=(popen_proc, ))
    proc_handler.start()

    return popen_proc, proc_handler

if __name__ == "__main__":
    print("OS: ", "windows" if is_windows() else ("unix" if is_unix() else "unknown"))