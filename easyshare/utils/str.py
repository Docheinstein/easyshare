import re
from typing import List, Pattern, Tuple, Any

from easyshare.utils.types import is_str


def keepchars(s: str, allowed: str) -> str:
    """
    Returns the characters of 's' there are in 'allowed'
    """
    ret = ""
    for c in s:
        if c in allowed:
            ret += c
    return ret


def discardchars(s: str, denied: str) -> str:
    """
    Returns the characters of 'd' there are not in 'denied'
    """

    return multireplace(s, [(d, "") for d in denied])


def satisfychars(s: str, allowed: str) -> bool:
    """
    Returns True if all the characters of 's' are in allowed
    """
    if not s or not allowed:
        return False
    for c in s:
        if c not in allowed:
            return False
    return True


def unprefix(s: str, prefix: str) -> str:
    """
    Removes 'prefix' from 's' if it starts with 'prefix'
    """
    if not s.startswith(prefix):
        return s
    return s[len(prefix):]


def rightof(s: str, sep: str, from_end=False) -> str:
    """
    Returns the part of 's' at the right of 'sep'
    or the original string if 'sep' is not found
    """
    if from_end:
        before, _, after_or_ori = s.rpartition(sep)
        return after_or_ori
    else:
        before_or_ori, _, after = s.partition(sep)
        if after:
            return after
        return before_or_ori


def leftof(s: str, sep: str, from_end=False) -> str:
    """
    Returns the part of 's' at the left of 'sep'
    or the original string if 'sep' is not found
    """
    if from_end:
        before, _, after_or_ori = s.rpartition(sep)
        if before:
            return before
        return after_or_ori
    else:
        before_or_ori, _, _ = s.partition(sep)
        return before_or_ori


def isorted(iterable, key = None):
    """ Case insensitive sorting. """

    def conv(o: Any):
        val = key(o) if key else o
        if is_str(val):
            val = val.lower()
        return val

    return sorted(iterable, key=lambda o: conv(o))


def multireplace(s: str,
                 str_replacements: List[Tuple[str, str]] = None,
                 re_replacements: List[Tuple[Pattern, str]] = None) -> str:
    """
    Performs multiple replacements, of literals or regex
    """

    if str_replacements:
        for k, v in str_replacements:
            s = s.replace(k, v)

    if re_replacements:
        for k, v in re_replacements:
            s = re.sub(k, v, s)

    return s

def chrnext(c: str, start: str, end: str) -> str:
    """
    Returns the char after c in the ASCII alphabet from base_start to base_end.
    e.g. chrnext('a', start='a', end='z') => b
         ...
         chrnext('z', start='a', end='z') => a
    """

    bs = ord(start)
    be = ord(end)

    if be < bs:
        bs, be = be, bs

    return chr((ord(c) - bs + 1) % (be - bs + 1) + bs)


def tf(cond, y: str = "true", n: str = "false") -> str:
    """ Returns 'y' if cond evaluates to True, 'n' otherwise """
    return y if cond else n

def yn(cond) -> str:
    """ Returns yes if cond evaluates to True, no otherwise """
    return tf(cond, "yes", "no")

def q(s) -> str:
    """ Returns str(s) with leading and trailing quotes """
    return '"' + str(s).strip('"') + '"'