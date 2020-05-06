from enum import Enum
from typing import List, Union

import colorama
import termcolor

from easyshare.utils.types import is_list


_colorful = True


class Color(Enum):
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"
    GREY = "grey"


class Style(Enum):
    BOLD = "bold"
    DARK = "dark"
    UNDERLINE = "underline"
    BLINK = "blink"
    REVERSE = "reverse"
    CONCEALED = "concealed"


def enable_colors(enabled: bool = True):
    global _colorful
    _colorful = enabled

    if enabled:
        colorama.init()


def styled(s: str, fg: Color = None, bg: Color = None, attrs: Union[Style, List[Style]] = None) -> str:
    attrs = attrs if is_list(attrs) else ([attrs] if attrs else None)
    return termcolor.colored(s,
                             color=fg.value if fg else None,
                             on_color="on_" + bg.value if bg else None,
                             attrs=[a.value for a in list(attrs)] if attrs else None) if _colorful else s


def fg(s: str, color: Color, attrs: Union[Style, List[Style]] = None) -> str:
    return styled(s, fg=color, attrs=attrs)


def bg(s: str, color: Color, attrs: Union[Style, List[Style]] = None) -> str:
    return styled(s, bg=color, attrs=attrs)


def red(s: str) -> str:
    return fg(s, Color.RED)


def green(s: str) -> str:
    return fg(s, Color.GREEN)


def yellow(s: str) -> str:
    return fg(s, Color.YELLOW)


def blue(s: str) -> str:
    return fg(s, Color.BLUE)


def magenta(s: str) -> str:
    return fg(s, Color.MAGENTA)


def cyan(s: str) -> str:
    return fg(s, Color.CYAN)


def white(s: str) -> str:
    return fg(s, Color.WHITE)


def grey(s: str) -> str:
    return fg(s, Color.GREY)


def redbg(s: str) -> str:
    return bg(s, Color.RED)


def greenbg(s: str) -> str:
    return bg(s, Color.GREEN)


def yellowbg(s: str) -> str:
    return bg(s, Color.YELLOW)


def bluebg(s: str) -> str:
    return bg(s, Color.BLUE)


def magentabg(s: str) -> str:
    return bg(s, Color.MAGENTA)


def cyanbg(s: str) -> str:
    return bg(s, Color.CYAN)


def whitebg(s: str) -> str:
    return bg(s, Color.WHITE)


def greybg(s: str) -> str:
    return bg(s, Color.GREY)
