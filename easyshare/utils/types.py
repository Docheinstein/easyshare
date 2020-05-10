from typing import Union, Any, Optional, List


# CHECKERS


def is_int(o: object) -> bool:
    return isinstance(o, int)


def is_str(o: object) -> bool:
    return isinstance(o, str)


def is_bool(o: object) -> bool:
    return isinstance(o, bool)


def is_bytes(o: object) -> bool:
    return isinstance(o, bytes)


def is_dict(o: dict) -> bool:
    return isinstance(o, dict)


def is_list(o: object) -> bool:
    return isinstance(o, list)


def is_valid_list(o: object) -> bool:
    return isinstance(o, list) and len(o) > 0


# CONVERTERS


def to_int(o: Any, default=None, raise_exceptions=False) -> Optional[int]:
    val = None
    try:
        val = int(o)
    except:
        pass

    if is_int(val):
        return val

    if raise_exceptions:
        raise ValueError("Conversion to integer failed")

    return default

def to_bool(o: Any, default=None, raise_exceptions=False) -> Optional[bool]:
    val = None
    try:
        if is_bool(o):
            val = o
        elif is_int(o):
            val = o != 0
        elif is_str(o):
            val = str_to_bool(o)
    except:
        pass

    if is_bool(val):
        return val

    if raise_exceptions:
        raise ValueError("Conversion to boolean failed")

    return default


def to_bytes(o: Any, default=None, raise_exceptions=False) -> Optional[bytes]:
    val = None
    try:
        if is_bytes(o):
            val = o
        elif is_str(o):
            val = str_to_bytes(o)
    except:
        pass

    if is_bytes(val):
        return val

    if raise_exceptions:
        raise ValueError("Conversion to bytes failed")

    return default


def str_to_bool(s: str, ystrings=None, nstrings=None, default=None) -> Union[bool, None]:
    if not ystrings:
        ystrings = ["true", "1", "yes", "y"]
    if not nstrings:
        nstrings = ["false", "0", "no", "n"]

    if s.lower() in ystrings:
        return True
    if s.lower() in nstrings:
        return False
    return default


def bool_to_str(b: bool, true: str = "true", false: str = "false", default: str = None) -> Optional[str]:
    if not is_bool(b):
        return default

    return true if b is True else false


def str_to_bytes(s: str) -> bytes:
    return bytes(s, encoding="UTF-8")


def bytes_to_str(b: bytes) -> str:
    return str(b, encoding="UTF-8")


def bytes_to_int(b: bytes, byteorder="big"):
    return int.from_bytes(b, byteorder)


def int_to_bytes(i: int, length,  byteorder="big"):
    return i.to_bytes(length, byteorder)


# MISC


def list_wrap(o: Any) -> List[Any]:
    if not o:
        return []
    if is_list(o):
        return o
    return [o]