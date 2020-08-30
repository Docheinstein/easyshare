from typing import Union, Any, Optional, List, Type


# MISC


def list_wrap(o: Any) -> List[Any]:
    if not o:
        return []
    if is_list(o):
        return o
    return [o]


# CHECKERS


def is_float(o: object) -> bool:
    return isinstance(o, float)


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


def is_list(o: object, oftype = None) -> bool:
    if not isinstance(o, list):
        return False
    if oftype:
        for i in o:
            if not isinstance(i, oftype):
                return False
    return True


def is_valid_list(o: object, oftype = None) -> bool:
    # noinspection PyTypeChecker
    return is_list(o, oftype) and len(o) > 0



# CONVERTERS

def to_type(o: Any, totype: Type, default=None, raise_exceptions=False):
    if not totype:
        return o
    if totype == str:
        return to_str(o, default=default, raise_exceptions=raise_exceptions)
    elif totype == int:
        return to_int(o, default=default, raise_exceptions=raise_exceptions)
    elif totype == float:
        return to_float(o, default=default, raise_exceptions=raise_exceptions)
    elif totype == bytes:
        return to_bytes(o, default=default, raise_exceptions=raise_exceptions)

def to_float(o: Any, default=None, raise_exceptions=False) -> Optional[int]:
    val = None
    try:
        val = float(o)
    except:
        pass

    if is_float(val):
        return val

    if raise_exceptions:
        try:
            err = ValueError("Conversion to float failed: {}".format(o))
        except:
            err = ValueError("Conversion to float failed")
        raise err

    return default


def to_int(o: Any, default=None, raise_exceptions=False) -> Optional[int]:
    val = None
    try:
        val = int(o)
    except:
        pass

    if is_int(val):
        return val

    if raise_exceptions:
        try:
            err = ValueError("Conversion to int failed: {}".format(o))
        except:
            err = ValueError("Conversion to int failed")
        raise err

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
        try:
            err = ValueError("Conversion to boolean failed: {}".format(o))
        except:
            err = ValueError("Conversion to boolean failed")
        raise err

    return default


def to_bytes(o: Any, default=None, raise_exceptions=False) -> Optional[bytes]:
    val = None
    try:
        if is_bytes(o):
            val = o
        elif is_str(o):
            val = stob(o)
    except:
        pass

    if is_bytes(val):
        return val

    if raise_exceptions:
        try:
            err = ValueError("Conversion to bytes failed: {}".format(o))
        except:
            err = ValueError("Conversion to bytes failed")
        raise err

    return default

def to_str(o: Any, default=None, raise_exceptions=False) -> Optional[str]:
    val = None
    try:
        if is_str(o):
            val = o
        elif is_int(o):
            val = str(o)
        elif is_bool(o):
            val = bool_to_str(o)
    except:
        pass

    if is_str(val):
        return val

    if raise_exceptions:
        try:
            err = ValueError("Conversion to str failed: {}".format(o))
        except:
            err = ValueError("Conversion to str failed")
        raise err

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


def bytes_to_str(b: Union[bytes, bytearray]) -> str:
    return str(b, encoding="UTF-8")


def bytes_to_int(b: Union[bytes, bytearray], byteorder="big") -> int:
    return int.from_bytes(b, byteorder)


def int_to_bytes(i: int, length,  byteorder="big") -> bytes:
    return i.to_bytes(length, byteorder)


# shortcuts

stob = str_to_bytes
btos = bytes_to_str
btoi = bytes_to_int
itob = int_to_bytes