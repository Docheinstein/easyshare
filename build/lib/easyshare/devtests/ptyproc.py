import time

from easyshare.utils.os import pty_detached

ptyproc = None

def out_hook(data):
    print(data, end="", flush=True)


def end_hook(data):
    print("END")


def writer():
    time.sleep(1)
    ptyproc.write("ls\n")

if __name__ == "__main__":
   ptyproc = pty_detached(out_hook=out_hook, end_hook=end_hook)
   writer()
   ptyproc.wait()