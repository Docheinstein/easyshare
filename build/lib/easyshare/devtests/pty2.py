import os
import pwd
import shlex
import pty

# from ptyprocess import PtyProcessUnicode, PtyProcess
import tty
from select import select
from subprocess import Popen, PIPE

from easyshare.utils.os import get_passwd


def pty_run(cmd = "/bin/sh"):
    # argv = shlex.split(cmd)

    # master_read = pty._read
    # stdin_read = pty._read

    master, slave = pty.openpty()
    proc = Popen(['/bin/sh'], preexec_fn=os.setsid, stdin=slave, stdout=PIPE, stderr=PIPE)
    os.fdopen(master, "w")

    print(master)
    print(slave)
    print(proc.stdin)
    print(proc.stdout)
    #
    #
    # try:
    #     mode = tty.tcgetattr(pty.STDIN_FILENO)
    #     tty.setraw(pty.STDIN_FILENO)
    #     restore = 1
    # except tty.error:  # This is the same as termios.error
    #     restore = 0


    try:
        #-------------

        # fds = [master_fd, pty.STDIN_FILENO]
        while True:
            rfds, wfds, xfds = select([proc.stdout], [], [])
            if proc.stdout in rfds:
                print("proc.stdout")
            elif proc.stdin in rfds:
                print("proc.stdin")
            #
            #     data = master_read(master_fd)
            #     if not data:  # Reached EOF.
            #         # print("\nRemoved master_fd from fds (EOF)")
            #         fds.remove(master_fd)
            #     else:
            #         # print("\nRead from master_fd: ", repr(data))
            #         os.write(pty.STDOUT_FILENO, data)
            # if pty.STDIN_FILENO in rfds:
            #     data = stdin_read(pty.STDIN_FILENO)
            #     if not data:
            #         # print("\nRemoved STDIN from fds")
            #         fds.remove(pty.STDIN_FILENO)
            #     else:
            #         # print(f"READ {data}")
            #         data = b"ls"
            #         pty._writen(master_fd, data)
            # os.close(master_fd)
            # (pid, retcode) = os.waitpid(pid, 0)
            # print(f"PID = {pid} exit ({retcode})")

    #--------------
    # except OSError:#
    finally:
        if restore:
            tty.tcsetattr(pty.STDIN_FILENO, tty.TCSAFLUSH, mode)





if __name__ == "__main__":
    # while True:
    #     cmd = input("$ ")
    #     if not cmd:
    #         continue
    #     p: PtyProcess = PtyProcessUnicode.spawn(shlex.split(cmd))
    #
    #     while True:
    #         try:
    #             l = p.readline()
    #             print(l, end="")
    #         except EOFError:
    #             break

    sh: pwd.struct_passwd = get_passwd()
    print(f"{sh.pw_uid} {sh.pw_name} : {sh.pw_shell}")

    pty_run()
    # while True:
    #     cmd = input("$ ")
    #     if not cmd:
    #         continue
