import sys

import colorama

from typing import List, Union, Optional
from easyshare.consts import ansi

_colorful = True


def enable_colors(enabled: bool = True):
    """ Enables/disables colors and styling of strings """
    global _colorful
    _colorful = enabled
    if enabled:
        if not are_colors_enabled():
            pass
            # print("Colors enabled but output stream doesn't support colors")
        colorama.init()
    else:
        pass
        # print("Colors disabled")


def are_colors_enabled():
    """ Returns whether colors are enabled """
    return _colorful


def styled(s: str,
           fg: Optional[str] = None,
           bg: Optional[str] = None,
           attrs: Union[str, List[str]] = ()) -> str:
    """ Styles the string with the given ansi escapes (foreground, background and attributes)"""
    if not _colorful:
        return s
    return _styled(s, fg, bg, *attrs)


def _styled(s: str, *attributes) -> str:
    ss = ""

    reset = ""
    for attr in attributes:
        if attr:
            ss += attr
            reset = ansi.RESET

    ss += s + reset

    return ss


def fg(s: str, color: str, *attributes) -> str:
    return styled(s, fg=color, bg=None, *attributes)


def bg(s: str, color: str, *attributes) -> str:
    return styled(s, fg=None, bg=color, *attributes)


def attrs(s: str, *attributes) -> str:
    return styled(s, fg=None, bg=None, *attributes)


def black(s: str) -> str:
    return fg(s, ansi.FG_BLACK)


def red(s: str) -> str:
    return fg(s, ansi.FG_RED)


def green(s: str) -> str:
    return fg(s, ansi.FG_GREEN)


def yellow(s: str) -> str:
    return fg(s, ansi.FG_YELLOW)


def blue(s: str) -> str:
    return fg(s, ansi.FG_BLUE)


def magenta(s: str) -> str:
    return fg(s, ansi.FG_MAGENTA)


def cyan(s: str) -> str:
    return fg(s, ansi.FG_CYAN)


def white(s: str) -> str:
    return fg(s, ansi.FG_WHITE)


def blackbg(s: str) -> str:
    return bg(s, ansi.BG_BLACK)


def redbg(s: str) -> str:
    return bg(s, ansi.BG_RED)


def greenbg(s: str) -> str:
    return bg(s, ansi.BG_GREEN)


def yellowbg(s: str) -> str:
    return bg(s, ansi.BG_YELLOW)


def bluebg(s: str) -> str:
    return bg(s, ansi.BG_BLUE)


def magentabg(s: str) -> str:
    return bg(s, ansi.BG_MAGENTA)


def cyanbg(s: str) -> str:
    return bg(s, ansi.BG_CYAN)


def whitebg(s: str) -> str:
    return bg(s, ansi.BG_WHITE)


def bold(s: str) -> str:
    return styled(s, attrs=ansi.ATTR_BOLD)


def underline(s: str) -> str:
    return styled(s, attrs=ansi.ATTR_UNDERLINE)


if __name__ == "__main__":
    import os
    from easyshare.utils.env import are_colors_supported

    colors_disabled = os.getenv('ANSI_COLORS_DISABLED')
    enable_colors(are_colors_supported() and not colors_disabled)

    print(cyan(f"CYAN on {sys.platform}, does it works?"))
    print(bold(f"BOLD on {sys.platform}, does it works?"))