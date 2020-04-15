from enum import Enum

import colorama
import termcolor

colorful = False


class Color(Enum):
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"


def init_colors(enabled: bool = True):
    global colorful
    colorful = enabled

    if enabled:
        colorama.init()


def colored(s: str, c: Color) -> str:
    return termcolor.colored(s, c.value) if colorful else s


def red(s: str) -> str:
    return colored(s, Color.RED)


def green(s: str) -> str:
    return colored(s, Color.GREEN)


def yellow(s: str) -> str:
    return colored(s, Color.YELLOW)


def blue(s: str) -> str:
    return colored(s, Color.BLUE)


def magenta(s: str) -> str:
    return colored(s, Color.MAGENTA)


def cyan(s: str) -> str:
    return colored(s, Color.CYAN)


def white(s: str) -> str:
    return colored(s, Color.WHITE)
