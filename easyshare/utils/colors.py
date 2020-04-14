from enum import Enum

import termcolor


class Color(Enum):
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"


def colored(s: str, c: Color) -> str:
    return termcolor.colored(s, c.value)


def red(s: str) -> str:
    return termcolor.colored(s, Color.RED.value)


def green(s: str) -> str:
    return termcolor.colored(s, Color.GREEN.value)


def yellow(s: str) -> str:
    return termcolor.colored(s, Color.YELLOW.value)


def blue(s: str) -> str:
    return termcolor.colored(s, Color.BLUE.value)


def magenta(s: str) -> str:
    return termcolor.colored(s, Color.MAGENTA.value)


def cyan(s: str) -> str:
    return termcolor.colored(s, Color.CYAN.value)


def white(s: str) -> str:
    return termcolor.colored(s, Color.WHITE.value)
