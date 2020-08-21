import ctypes
from ctypes import c_int, CDLL, c_char_p, c_void_p, cast
from typing import Callable, Union

from easyshare.logging import get_logger
from easyshare.utils.types import is_bytes, is_str

log = get_logger(__name__)

class CException(Exception):
    pass

# Loading

def load_library(name: str):
    try:
        return ctypes.CDLL(name)
    except Exception as e:
        log.w(f"load_library failed: {e}")
        raise CException(e)


# Utils

def c_btos(b: bytes) -> str:
    return str(b, encoding="ascii")

def c_stob(s: str) -> bytes:
    return s.encode("ascii")


# int


def set_int(lib: CDLL, name: str, value: int):
    try:
        c_int.in_dll(lib, name).value = value
    except Exception as e:
        log.w(f"set_int failed: {e}")
        raise CException(e)

def get_int(lib: CDLL, name: str) -> int:
    try:
        return c_int.in_dll(lib, name).value
    except Exception as e:
        log.w(f"get_int failed: {e}")
        raise CException(e)


# char *


def set_char_p(lib: CDLL, name: str, value: Union[bytes, str]):
    try:
        if is_str(value):
            value = c_stob(value)
        elif not is_bytes(value):
            raise TypeError(f"Exception bytes or str, found {type(value)}")

        c_char_p.in_dll(lib, name).value = value
    except Exception as e:
        log.w(f"set_char_p failed: {e}")
        raise CException(e)

def get_char_p(lib: CDLL, name: str) -> str:
    try:
        return c_btos(c_char_p.in_dll(lib, name).value)
    except Exception as e:
        log.w(f"get_char_p failed: {e}")
        raise CException(e)


# function pointer


def set_func_ptr(lib: CDLL, name: str, func: Callable, prototype):
    try:
        c_void_p.in_dll(lib, name).value = cast(prototype(func), c_void_p).value
    except Exception as e:
        log.w(f"set_func_ptr failed: {e}")
        raise CException(e)
