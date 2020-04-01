import json
import logging
import random
import string
import sys
from collections import Set, Mapping
from typing import Any, Union


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


def is_valid_list(o: object) -> bool:
    return is_list(o) and len(o) > 0


def filter_string(s: str, allowed: str) -> str:
    ret = ""
    for c in s:
        if c in allowed:
            ret += c
    return ret


def respects(s: str, allowed: str) -> bool:
    for c in s:
        if c not in allowed:
            return False
    return True


def strip_prefix(s: str, prefix: str) -> str:
    if not s.startswith(prefix):
        return s
    return s.split(prefix)[1]


def strip(s: str, chars: str) -> str:
    if not s:
        return s
    return s.strip(chars)


def strip_quotes(s: str) -> str:
    return strip(s, chars="\"'")


def to_bool(o: object) -> Union[bool, None]:
    if isinstance(o, bool):
        return o
    if isinstance(o, int):
        return o != 0
    if isinstance(o, str):
        return str_to_bool(o)
    return None


def is_int(o: object) -> bool:
    return isinstance(o, int)


def is_str(o: object) -> bool:
    return isinstance(o, str)


def is_list(o: object) -> bool:
    return isinstance(o, list)



def str_to_bool(s: str) -> Union[bool, None]:
    if s.lower() in ["true", "1", "yes", "y"]:
        return True
    if s.lower() in ["false", "0", "no", "n"]:
        return False
    return None


def to_int(o: Any) -> Union[int, None]:
    try:
        return int(o)
    except Exception:
        return None


def bytes_to_int(b: bytes, byteorder="big"):
    return int.from_bytes(b, byteorder)


def to_json_str(o: object, pretty=False):
    if pretty:
        return json.dumps(o, indent=4)
    return json.dumps(o, separators=(",", ":"))


def str_to_bytes(s: str):
    return bytes(s, encoding="UTF-8")


G = 1000000000
M = 1000000
K = 1000


def size_str(size: int, fmt="{:0.1f} {}", identifiers=(" ", "K", "M", "G")):
    if size > G:
        return fmt.format(size / G, identifiers[3])
    if size > M:
        return fmt.format(size / M, identifiers[2])
    if size > K:
        return fmt.format(size / K, identifiers[1])
    return fmt.format(size, identifiers[0])
