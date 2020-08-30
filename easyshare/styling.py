import colorama

from typing import List, Union, Optional
from easyshare.consts import ansi
from easyshare.settings import add_setting_callback, Settings, SettingValue, get_setting

_styling_cached = None

def init_styling():
    global _styling_cached

    def on_colors_changed(key: str, val: SettingValue):
        global _styling_cached
        _styling_cached = val
        if _styling_cached:
            colorama.init()

    _styling_cached = get_setting(Settings.COLORS)
    add_setting_callback(Settings.COLORS, on_colors_changed)

def is_styling_enabled():
    return _styling_cached

def styled(s: str,
           fg: Optional[str] = None,
           bg: Optional[str] = None,
           attrs: Union[str, List[str]] = ()) -> str:
    """ Styles the string with the given ansi escapes (foreground, background and attributes)"""
    if not _styling_cached:
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