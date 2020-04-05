# CHECKERS
from typing import Union, Any


def is_int(o: object) -> bool:
    return isinstance(o, int)


def is_str(o: object) -> bool:
    return isinstance(o, str)


def is_dict(o: dict) -> bool:
    return isinstance(o, dict)


def is_list(o: object) -> bool:
    return isinstance(o, list)


def is_valid_list(o: object) -> bool:
    return isinstance(o, list) and len(o) > 0


# CONVERTERS

def to_int(o: Any) -> Union[int, None]:
    try:
        return int(o)
    except Exception:
        return None


def to_bool(o: object) -> Union[bool, None]:
    if isinstance(o, bool):
        return o
    if isinstance(o, int):
        return o != 0
    if isinstance(o, str):
        return str_to_bool(o)
    return None


def str_to_bool(s: str, ystrings=None, nstrings=None) -> Union[bool, None]:
    if not ystrings:
        ystrings = ["true", "1", "yes", "y"]
    if not nstrings:
        nstrings = ["false", "0", "no", "n"]

    if s.lower() in ystrings:
        return True
    if s.lower() in nstrings:
        return False
    return None


def str_to_bytes(s: str):
    return bytes(s, encoding="UTF-8")


def bytes_to_int(b: bytes, byteorder="big"):
    return int.from_bytes(b, byteorder)


def int_to_bytes(i: int, length,  byteorder="big"):
    return i.to_bytes(length, byteorder)




