import string
import random


def randstring(length=16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join([random.choice(alphabet) for _ in range(length)])


def keep(s: str, allowed: str) -> str:
    ret = ""
    for c in s:
        if c in allowed:
            ret += c
    return ret


def satisfy(s: str, allowed: str) -> bool:
    for c in s:
        if c not in allowed:
            return False
    return True


def unprefix(s: str, prefix: str) -> str:
    if not s.startswith(prefix):
        return s
    return s.split(prefix)[1]


# def strip(s: str, chars: str) -> str:
#     if not s:
#         return s
#     return s.strip(chars)
