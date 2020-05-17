import sys
from typing import NoReturn


def eprint(*args, **kwargs):
    """ Prints to stderr. """
    print(*args, file=sys.stderr, **kwargs)


def terminate(message = None) -> NoReturn:
    """ Exit GRACEFULLY with the given message and exit code """
    if message:
        print(message)
    exit(0)


def abort(message = None, exit_code = 1) -> NoReturn:
    """ Exit UNGRACEFULLY with the given message and exit code. """
    if message:
        eprint(message)
    exit(exit_code)
