from typing import List, Union, Optional

import colorama

from easyshare.consts import ansi

_colorful = True

def enable_colors(enabled: bool = True):
    global _colorful
    _colorful = enabled

    if enabled:
        colorama.init()

def styled(s: str,
           fg: Optional[ansi.ansi_fg] = None,
           bg: Optional[ansi.ansi_bg] = None,
           attrs: Union[ansi.ansi_attr, List[ansi.ansi_attr]] = ()) -> str:
    if not _colorful:
        return s
    return _styled(s, fg, bg, *attrs)


def _styled(s: str, *attributes)-> str:
    ss = ""

    for attr in attributes:
        if attr:
            ss += attr

    ss += s + ansi.RESET

    return ss

def fg(s: str, color: ansi.ansi_fg, *attributes) -> str:
    return styled(s, fg=color, bg=None, *attributes)


def bg(s: str, color: ansi.ansi_bg, *attributes) -> str:
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
    print(red("Hello"))
    print(bold("Hello"))
    print(red(bold("Hello")))

    print(ansi.ATTR_BOLD + "Hello")
    print("Should ne non-bold" + ansi.RESET)

