import errno
import fcntl
import os
import pty
import select
import shlex
import shutil
import subprocess
import threading
import tty
from pathlib import Path
from pwd import getpwuid, struct_passwd
from typing import Optional, List, Union, Tuple, Any, Callable

from ptyprocess import PtyProcess, PtyProcessUnicode

from easyshare.logging import get_logger
from easyshare.protocol.types import FTYPE_DIR, FileInfoTreeNode, FileInfo, create_file_info
from easyshare.utils.path import is_hidden
from easyshare.utils.types import list_wrap, bytes_to_str

log = get_logger(__name__)


def is_unix():
    return os.name == "posix"

def is_windows():
    return os.name == "nt"


def get_passwd() -> struct_passwd:
    return getpwuid(os.geteuid())

def is_relpath(s: str) -> bool:
    raise ValueError("not impl")
    # s = pathify(s)
    # return not s.startswith(os.sep)

# def is_hidden(s):
#     raise ValueError("not impl")

def is_abspath(s: str) -> bool:
    raise ValueError("not impl")
    # s = pathify(s)
    # return s.startswith(os.sep)


def relpath(s: str) -> str:
    raise ValueError("not impl")
    # s = pathify(s)
    # return s.lstrip(os.sep)


def abspath(s: str) -> str:
    raise ValueError("not impl")
    # s = pathify(s)
    # return s if is_abspath(s) else (os.sep + s)


# def pathify(s: str) -> str:
#     return os.path.expanduser(s)

# def parent_dir(p: Path):
#     # os.path.split() differs from pathlib.parent
#     # pathlib.parent of /home/user/ is "/home"
#     # os.path.split of /home/user/ is ("/home/user/", "")
#     return p if str(p).endswith(os.path.sep) else p.parent

def ls(path: Path,
       sort_by: Union[str, List[str]] = "name",
       reverse: bool = False,
       hidden: bool = False) -> Optional[List[FileInfo]]:
    if not path:
        raise TypeError("found invalid path")

    sort_by = list(filter(lambda field: field in ["name", "size", "ftype"],
                          list_wrap(sort_by)))

    log.i("LS sorting by %s%s", sort_by, " (reverse)" if reverse else "")

    ret: List[FileInfo] = []

    # Single file
    if path.is_file():
        # Show it even if it is hidden
        return [create_file_info(path)]

    if not path.is_dir():
        log.e("Cannot perform ls; invalid path")
        raise FileNotFoundError()

    # Directory
    p: Path
    for p in path.iterdir():

        if not hidden and is_hidden(p):
            log.d("Not showing hidden file: %s", p)
            continue

        ret.append(create_file_info(p))

    # Sort the result for each field of sort_by
    for sort_field in sort_by:
        ret = sorted(ret, key=lambda fi: fi[sort_field])

    if reverse:
        ret.reverse()

    return ret


def tree(path: Path,
         sort_by: Union[str, List[str]] = "name",
         reverse: bool = False,
         max_depth: int = None,
         hidden: bool = False) -> Optional[FileInfoTreeNode]:
    if not path:
        raise TypeError("found invalid path")

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
            # Compute children of this directory, just the first time

            # It might fail (e.g. permission denied)
            # TODO: unix tree reports the descend error too
            # in the future we could do it
            try:
                cursor["children_unseen_info"] = ls(cur_path,
                                                    sort_by=sort_by,
                                                    reverse=reverse,
                                                    hidden=hidden)
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

        # There is an unseen child, take it out
        unseen_child_info = cursor.get("children_unseen_info").pop(0)

        # Add it to the children of this node
        cursor.setdefault("children", [])

        child = dict(
            unseen_child_info,
            parent=cursor,
            path=cur_path.joinpath(unseen_child_info.get("name"))
        )

        cursor.get("children").append(child)

        # Go down to this child
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



def rm(path: Path, error_callback: Callable[[Exception, Path], None] = None) -> bool:
    if not path:
        raise TypeError("found invalid path")


    # Catch everything, and report any error to error_callback if it's valid
    try:
        if path.is_file():
            log.d("unlink since '%s' is a file", path)
            path.unlink()
            return True

        if not path.is_dir():
            log.e("Cannot perform rm; invalid path")
            raise FileNotFoundError()

        def handle_rmtree_error(error_func,
                                error_path: Path,
                                error_excinfo: Tuple[Any, Exception, Any]):

            excinfo_class, excinfo_error, excinfo_traceback = error_excinfo

            log.e("rm error occurred on path '%s': %s", error_path, excinfo_error)

            # Notify the observer
            if error_callback:
                error_callback(excinfo_error, Path(error_path))

        log.d("rmtree since '%s' is a directory", path)
        ignore_errors = False if error_callback else True
        shutil.rmtree(path, ignore_errors=ignore_errors, onerror=handle_rmtree_error)

    except Exception as ex:
        # Notify the exception if error_callback is valid
        log.e("rm error occurred on path '%s': %s", path, ex)
        if error_callback:
            error_callback(ex, path)
        else:
            raise ex

def mv(src: Path, dest: Path):
    shutil.move(str(src), str(dest))


def cp(src: Path, dest: Path):
    # shutil.copy doesn't handle directories recursively as move
    # we have to use copytree if we detect a DIR to DIR copy
    if src.is_dir() and dest.is_dir():
        log.d("Recursive copy DIR => DIR detected")
        dest = dest.joinpath(src.name)
        log.d("Definitive src = '%s' | dst = '%s'", src, dest)
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest), follow_symlinks=False)


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

    proc_handler_th = threading.Thread(target=proc_handler, daemon=True, args=(popen_proc, ))
    proc_handler_th.start()

    return popen_proc, proc_handler

def pty_attached(cmd: str = "/bin/sh") -> int:
    argv = shlex.split(cmd)

    master_read = pty._read
    stdin_read = pty._read

    pid, master_fd = pty.fork()
    if pid == pty.CHILD:
        os.execlp(argv[0], *argv)
    try:
        mode = tty.tcgetattr(pty.STDIN_FILENO)
        tty.setraw(pty.STDIN_FILENO)
        restore = 1
    except tty.error:  # This is the same as termios.error
        restore = 0
    try:
        pty._copy(master_fd, master_read, stdin_read)
    except OSError:#
        pass
    finally:
        if restore:
            tty.tcsetattr(pty.STDIN_FILENO, tty.TCSAFLUSH, mode)

    os.close(master_fd)

    (pid, retcode) = os.waitpid(pid, 0)
    return retcode


def pty_detached(out_hook: Callable[[str], None],
                 end_hook: Callable[[int], None],
                 cmd: str = "/bin/sh") -> PtyProcess:
    argv = shlex.split(cmd)
    ptyproc = PtyProcessUnicode.spawn(argv)

    def proc_handler():
        while True:
            try:
                data = ptyproc.read()
                out_hook(data)
            except OSError:
                break
            except EOFError:
                break
        end_hook(0)

    proc_handler_th = threading.Thread(target=proc_handler, daemon=True)
    proc_handler_th.start()

    return ptyproc


def os_error_str(err: OSError):
    """ Returns the explanation of the error (e.g. Directory not empty) """
    if isinstance(err, OSError):
        if err and err.strerror:
            return err.strerror
        log.exception("Unknown OS error")
        serr = str(err)
        return serr or "Error" # fallback
    return "Error" # fallback

if __name__ == "__main__":
    print("OS: ", "windows" if is_windows() else ("unix" if is_unix() else "unknown"))