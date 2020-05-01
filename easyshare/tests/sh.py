import fcntl
import os
import select
import sys

from easyshare.utils.colors import red
from easyshare.utils.os import run_detached, stdin_read_nonblocking
from easyshare.utils.types import bytes_to_str


def rprint(s, *args, **kwargs):
    print(red(s), *args, **kwargs)


def stdout_hook(line):
    print(line, end="", flush=True)


def end_hook(retcode):
    print("END: ", retcode)



def exec_command(cmd):

    proc, handler = run_detached(
        cmd,
        stdout_hook=stdout_hook,
        end_hook=end_hook
    )

    def on_stdin(line):
        nonlocal proc

        if proc.poll() is None:
            proc.stdin.write(line)
            proc.stdin.flush()
        else:
            rprint("not sending data since command already finished")

    def on_eof():
        nonlocal proc

        if proc.poll() is None:
            proc.stdin.close()
        else:
            rprint("not sending EOF since command already finished")

    stdin_read_nonblocking(
        continue_condition=lambda: proc.poll() is None,
        stdin_hook=on_stdin,
        eof_hook=on_eof,
    )

    handler.join()



if __name__ == "__main__":


    while True:
        try:
            command = input("$ ")
            exec_command(command)
        except KeyboardInterrupt:
            print("=============")
