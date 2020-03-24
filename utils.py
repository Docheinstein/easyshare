import logging
import random
import string
import sys


def eprint(*args, **kwargs):
    """
    Prints to stderr.
    :param args: arguments argument to pass to print()
    :param kwargs: keyword argument to pass to print()
    """
    print(*args, file=sys.stderr, **kwargs)


def terminate(message, exit_code=0):
    """
    Exit gracefully with the given message and exit code.
    :param message: the message to print to stdout before exit
    :param exit_code: the exit code
    """
    print(message)
    exit(exit_code)


def abort(message, exit_code=-1):
    """
    Exit ungracefully with the given message and exit code.
    :param message: the message to print to stderr before exit
    :param exit_code: the exit code
    """
    logging.error(message)
    eprint(message)
    exit(exit_code)


def items(obj):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("__")}

def values(obj):
    return [v for k, v in obj.__dict__.items() if not k.startswith("__")]

def keys(obj):
    return [k for k, v in obj.__dict__.items() if not k.startswith("__")]

def random_string(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join([random.choice(alphabet) for _ in range(length)])
