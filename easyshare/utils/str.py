import re
import string
import random
from typing import List, Dict, Pattern, Tuple
from uuid import uuid4 as UUID
from easyshare.utils.types import is_str


def strstr(s: str) -> str:
    return "\"" + s + "\"" if is_str(s) else str(s)


def randstring(length=16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join([random.choice(alphabet) for _ in range(length)])


def uuid() -> str:
    return UUID().hex


def keep(s: str, allowed: str) -> str:
    ret = ""
    for c in s:
        if c in allowed:
            ret += c
    return ret


def discard(s: str, denied: str) -> str:
    return multireplace(s, [(d, "") for d in denied])


def satisfy(s: str, allowed: str) -> bool:
    if not s or not allowed:
        return False
    for c in s:
        if c not in allowed:
            return False
    return True


def unprefix(s: str, prefix: str) -> str:
    if not s.startswith(prefix):
        return s
    return s[len(prefix):]


def rightof(s: str, sep: str, from_end=False) -> str:
    if from_end:
        before, _, after_or_ori = s.rpartition(sep)
        return after_or_ori
    else:
        before_or_ori, _, after = s.partition(sep)
        if after:
            return after
        return before_or_ori


def leftof(s: str, sep: str, from_end=False) -> str:
    if from_end:
        before, _, after_or_ori = s.rpartition(sep)
        if before:
            return before
        return after_or_ori
    else:
        before_or_ori, _, _ = s.partition(sep)
        return before_or_ori


def sorted_i(l: List[str], in_subset: str = None, not_in_subset: str = None):
    def s_conv(s: str):
        if not_in_subset:
            s = discard(s, not_in_subset)
        if in_subset:
            s = keep(s, in_subset)
        return s.lower()

    return sorted(l, key=lambda s: s_conv(s))


def multireplace(s: str,
                 str_replacements: List[Tuple[str, str]],
                 re_replacements: List[Tuple[Pattern, str]] = None) -> str:

    if str_replacements:
        for k, v in str_replacements:
            s = s.replace(k, v)

    if re_replacements:
        for k, v in re_replacements:
            s = re.sub(k, v, s)

    return s

# def multireplace_re(s: str, table: Dict[str, str]) -> str:
#     for k, v in table.items():
#         s = re.sub()
#     return s


