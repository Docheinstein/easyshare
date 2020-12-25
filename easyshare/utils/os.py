import os
import re
import shutil
import threading
import time
from collections import deque
from math import ceil
from os import PathLike
from pathlib import Path
from stat import S_ISREG
from typing import Optional, List, Union, Tuple, Any, Callable

from easyshare.logging import get_logger
from easyshare.protocol.types import FTYPE_DIR, FileInfoTreeNode, FileInfo, create_file_info, FileType
from easyshare.utils.env import is_unix
from easyshare.utils.path import is_hidden
from easyshare.utils.str import isorted
from easyshare.utils.types import list_wrap

log = get_logger(__name__)

_PERM_DIGIT_STR = {
    "0": "---",
    "1": "--x",
    "2": "-w-",
    "3": "-wx",
    "4": "r--",
    "5": "r-x",
    "6": "rw-",
    "7": "rwx",
}


if is_unix():
    from pwd import getpwuid, struct_passwd
    from grp import getgrgid, struct_group
    from ptyprocess import PtyProcess
    import tty
    import pty


    def user(uid = os.geteuid()) -> struct_passwd:
        """
        Get the user entry for the given user id
        (or the current one if not specified)
        """
        return getpwuid(uid)

    def group(gid = os.getgid()) -> struct_group:

        """
        Get the group entry for the given group id
        (or the current one if not specified)
        """
        return getgrgid(gid)
else:
    def user(uid):
        raise ValueError("Not implemented")

    def group(gid):
        raise ValueError("Not implemented")


def os_error_str(err: OSError):
    """ Returns the explanation of the error (e.g. Directory not empty) """
    if isinstance(err, OSError):
        if err and err.strerror:
            return err.strerror
        log.eexception("Unknown OS error")
        serr = str(err)
        return serr or "Error" # fallback
    return "Error" # fallback


def perm_str(perm: str):
    return \
        _PERM_DIGIT_STR.get(perm[0], "---") + \
        _PERM_DIGIT_STR.get(perm[1], "---") + \
        _PERM_DIGIT_STR.get(perm[2], "---")


def set_mtime(f: Union[str, Path], mtime: int, round_up=False):
    # It seems that on some platform (e.g. android/termux) utime() is not
    # able to set the mtime with ns precision.
    # In order to avoid to lose precision, which will lead to some bugs
    # regarding the mtime of the files when transferring based on mtime (e.g get -s),
    # using round_up=True increase the mtime (instead of let it being decreased)
    # to the upper second
    mtime = mtime if not round_up else ceil(mtime * 10 ** (-9)) * 10 ** 9
    os.utime(f, ns=(time.clock_gettime_ns(time.CLOCK_REALTIME), mtime))

def is_newer(t1: Union[str, Path, int], t2: Union[str, Path, int], threshold=1e9):
    """ Returns whether t1 is newer (mtime) compared to t2, within a threshold """
    # threshold is the ns within the file is considered not newer, even if it is
    # default is one second
    t1 = t1 if isinstance(t1, int) else Path(t1).stat().st_mtime_ns
    t2 = t2 if isinstance(t2, int) else Path(t2).stat().st_mtime_ns
    return t1 > t2 + threshold


def ls(path: Path,
       sort_by: Union[str, List[str]] = "name",
       reverse: bool = False,
       hidden: bool = False,
       details: bool = False) -> List[FileInfo]:
    """ Wrapper of Path.iterdir() that provides a list of FileInfo """

    if not path:
        raise TypeError("found invalid path")

    sort_by = list(filter(lambda field: field in ["name", "size", "ftype"],
                          list_wrap(sort_by)))

    log.i("LS")

    ret: List[FileInfo] = []

    # Single file
    if path.is_file():
        # Show it even if it is hidden
        finfo = create_file_info(path,
                                 fetch_size=details, fetch_time=details,
                                 fetch_perm=details, fetch_owner=details)
        if not finfo:
            return []
        return [finfo]

    if not path.is_dir():
        log.e("Cannot perform ls; invalid path")

        raise FileNotFoundError()

    # Directory
    p: Path
    for p in path.iterdir():

        if not hidden and is_hidden(p):
            log.d(f"Not showing hidden file: {p}")
            continue
        finfo = create_file_info(p,
                                 fetch_size=details, fetch_time=details,
                                 fetch_perm=details, fetch_owner=details)
        if finfo:
            ret.append(finfo)

    # Sort the result for each field of sort_by
    for sort_field in sort_by:
        ret = isorted(ret, key=lambda fi: fi[sort_field])

    if reverse:
        ret.reverse()

    return ret


def tree(path: Path,
         sort_by: Union[str, List[str]] = "name",
         reverse: bool = False,
         max_depth: int = None,
         hidden: bool = False,
         details: bool = False) -> Optional[FileInfoTreeNode]:
    """
    Performs a traversal from the given 'path' and provide a 'FileInfoTreeNode'
    that represent the tree structure.
    """
    if not path:
        raise TypeError("found invalid path")

    path = path.resolve()

    sort_by = list(filter(lambda field: field in ["name", "size", "ftype"],
                          list_wrap(sort_by)))

    log.i("TREE on {}, sorting by {}{}".format(path, sort_by, " (reverse)" if reverse else ""))

    if not path.exists():
        log.e("Cannot perform tree; invalid path")
        raise FileNotFoundError()

    root: Any = create_file_info(path,
                                 fetch_size=details, fetch_time=details,
                                 fetch_perm=details, fetch_owner=details)

    if not root:
        return None

    root["path"] = path

    cursor = root
    depth = 0

    while True:
        cur_path: Path = cursor.get("path")
        cur_ftype: FileInfo = cursor.get("ftype")

        if cur_ftype == FTYPE_DIR and "children_unseen_info" not in cursor\
                and (not max_depth or depth < max_depth):
            # Compute children of this directory, just the first time

            # It might fail (e.g. permission denied)
            # TODO: unix tree reports the descend error too
            # in the future we could do it
            try:
                cursor["children_unseen_info"] = ls(cur_path,
                                                    sort_by=sort_by,
                                                    reverse=reverse,
                                                    hidden=hidden,
                                                    details=details)
            except OSError:
                log.w(f"Cannot descend {cur_path}")
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

        # There is an unseen child, take it out
        unseen_child_info = cursor.get("children_unseen_info").pop(0)

        # Add it to the children of this node
        cursor.setdefault("children", [])

        child = dict(
            unseen_child_info,
            parent=cursor,
            path=cur_path / unseen_child_info.get("name")
        )


        cursor.get("children").append(child)

        # Go down to this child
        cursor = child
        depth += 1

    return root


def find(path: Union[Path, PathLike],
         name: str = None,
         regex: str = None,
         case_sensitive: bool = True,
         ftype: FileType = None,
         max_depth: int = None,
         details: bool = False,
         file_info_name_provider: Callable[[Path], str] = str) -> Optional[List[FileInfo]]:

    if not path:
        raise TypeError("found invalid path")

    log.i("FIND searching\n"
          f"\tname={name}\n"
          f"\tregex={regex}\n"
          f"\tcase_sensitive={case_sensitive}\n"
          f"\tftype={ftype}\n"
          f"\tmax_depth={max_depth}\n"
          f"\tdetails={details}")

    name_filter = None
    regex_filter = None
    ftype_filter = ftype

    if name:
        name_filter = name
        if not case_sensitive:
            name_filter = name_filter.lower()

    if regex:
        flags = 0
        if not case_sensitive:
            flags = re.IGNORECASE
        try:
            regex_filter = re.compile(regex, flags)
            log.d("Regex compiled successfully")
        except:
            log.w(f"Invalid regex pattern: {regex}")
            return None

    ret: List[FileInfo] = []

    if not path.exists():
        return ret

    for f, fstat in walk_preorder(path, max_depth=max_depth):
        p = Path(f)
        finfo = create_file_info(p,
                                 fstat=fstat,
                                 name=file_info_name_provider(p),
                                 fetch_size=details, fetch_time=details,
                                 fetch_perm=details, fetch_owner=details)
        if not finfo:
            continue

        log.d(f"finfo = {finfo}")
        f_name = finfo.get("name")

        path_filter_subject = f_name

        if case_sensitive is False:
            path_filter_subject = path_filter_subject.lower()

        # Check if satisfy the filter
        if name_filter:
            if name_filter not in path_filter_subject:
                log.d("-> name filter failed")
                continue
        if regex_filter:
            if not re.search(regex_filter, path_filter_subject):
                log.d("-> regex filter failed")
                continue

        # Filename filters passed

        # Type filters
        ftype = finfo.get("ftype")
        if ftype_filter and ftype_filter != ftype:
            log.d("-> ftype filter failed")
            continue

        log.i(f"find ok: {f_name}")
        ret.append(finfo)


    return ret


def du(path: Path):

    if not path:
        raise TypeError("found invalid path")

    if not path.exists():
        raise FileNotFoundError()

    log.i(f"DU {path}")

    du_sum = 0

    for f, fstat in walk_preorder(path):
        du_sum += fstat.st_size

    log.i(f"DU total: {du_sum}B")

    return du_sum


def walk_preorder(path: Path, max_depth: int = None):
    root = path
    log.d(f"walk_preorder over '{root}' - max_depth={max_depth}")

    stack: deque = deque([(root, 0)])
    # stack: List[Path] = [root]

    while stack:
        cursor_path, cursor_depth = stack.popleft()
        # cursor = stack.pop(0)

        try:
            fstat = cursor_path.stat()
        except OSError as oserr:
            log.w(f"Can't stat: {oserr}")
            continue

        try:
            is_file = S_ISREG(fstat.st_mode)
        except OSError:
            is_file = False

        if is_file:
            yield cursor_path, fstat
        else: # probably is_dir
            if cursor_path != root:
                yield cursor_path, fstat

            # Descend further, if allowed by max depth
            if max_depth is None or cursor_depth < max_depth:
                try:
                    children: List = [(c, cursor_depth + 1) for c in isorted(list(cursor_path.iterdir()))]
                    stack.extendleft(reversed(children))
                    # stack = children + stack
                except OSError as oserr:
                    log.w(f"Can't descend: {oserr}")
            else:
                log.d(f"cursor_depth({cursor_depth}) > max_depth({max_depth}) - not descending further")


def rm(path: Path, error_callback: Callable[[Exception, Path], None] = None) -> bool:
    """
    Wrapper that remove path either if it is a file or a (even filled) directory.
    Reports the errors to error_callback.
    """
    if not path:
        raise TypeError("found invalid path")


    # Catch everything, and report any error to error_callback if it's valid
    try:
        if path.is_file():
            log.d(f"unlink since '{path}' is a file")
            path.unlink()
            return True

        if not path.is_dir():
            log.e("Cannot perform rm; invalid path")
            raise FileNotFoundError()

        def handle_rmtree_error(error_func,
                                error_path: Path,
                                error_excinfo: Tuple[Any, Exception, Any]):

            excinfo_class, excinfo_error, excinfo_traceback = error_excinfo

            log.e(f"rm error occurred on path '{error_path}': {excinfo_error}")

            # Notify the observer
            if error_callback:
                error_callback(excinfo_error, Path(error_path))

        log.d(f"rmtree since '{path}' is a directory")
        ignore_errors = False if error_callback else True
        shutil.rmtree(path, ignore_errors=ignore_errors, onerror=handle_rmtree_error)

    except Exception as ex:
        # Notify the exception if error_callback is valid
        log.e(f"rm error occurred on path '{path}': {ex}")
        if error_callback:
            error_callback(ex, path)
        else:
            raise ex

def mv(src: Path, dest: Path):
    """ Moves src to dest, even recursively """
    shutil.move(str(src), str(dest))


def cp(src: Path, dest: Path):
    """ Copies src to dest, even recursively """

    # shutil.copy doesn't handle directories recursively as move
    # we have to use copytree if we detect a DIR to DIR copy
    if src.is_dir() and dest.is_dir():
        log.d("Recursive copy DIR => DIR detected")
        dest = dest / src.name
        log.d(f"Definitive src = '{src}' | dst = '{dest}'")
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest), follow_symlinks=False)


def pty_attached(cmd: str = "/bin/sh") -> int:
    """
    Run a command in a pseudo terminal, while being attached to this terminal.
    """
    exec_bin = "/bin/sh"
    exec_args = [exec_bin, "-c", cmd]

    master_read = pty._read
    stdin_read = pty._read

    pid, master_fd = pty.fork()
    if pid == pty.CHILD:
        log.d(f"os.execv({exec_bin}, {exec_args})")
        os.execv(exec_bin, exec_args)

    tty_mode = None
    try:
        tty_mode = tty.tcgetattr(pty.STDIN_FILENO)
        tty.setraw(pty.STDIN_FILENO)
    except tty.error:
        pass

    try:
        pty._copy(master_fd, master_read, stdin_read)
    except OSError:
        pass
    finally:
        if tty_mode:
            tty.tcsetattr(pty.STDIN_FILENO, tty.TCSAFLUSH, tty_mode)

    os.close(master_fd)

    (pid, retcode) = os.waitpid(pid, 0)
    return retcode


def pty_detached(out_hook: Callable[[bytes], None],
                 end_hook: Callable[[int], None],
                 cols: int,
                 rows: int,
                 cmd: str = "/bin/sh"):  # -> PtyProcess:
    """
    Run a command, reporting stdout and stderr of the process outside (via out_hook).
    The stdin can be provided with ptyproc.write().
    """

    exec_bin = "/bin/sh"
    exec_args = [exec_bin, "-c", cmd]

    log.d(f"PtyProcess.spawn({exec_bin}, {exec_args}) - size =({cols}, {rows})")

    ptyproc = PtyProcess.spawn(exec_args, dimensions=(rows, cols), echo=False)

    def proc_handler():
        retcode = 0
        while True:
            try:
                data = ptyproc.read()
                out_hook(data)
            except EOFError:
                break # CTRL+D => quit the shell
            except Exception:
                retcode = -1
                break # Consider any exception as a shell failure
        end_hook(retcode) # TODO how get the real return code?

    proc_handler_th = threading.Thread(target=proc_handler, daemon=True)
    proc_handler_th.start()

    return ptyproc

if __name__ == "__main__":
    import sys
    print(is_newer(sys.argv[1], sys.argv[2]))