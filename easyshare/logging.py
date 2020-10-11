import sys
import traceback

from easyshare.common import easyshare_setup, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO, VERBOSITY_DEBUG, \
    VERBOSITY_MAX, VERBOSITY_MIN, VERBOSITY_HUGE
from easyshare.settings import get_setting, Settings
from easyshare.styling import yellow, red, green, blue, magenta, black

# TODO: convert %s to format string
from easyshare.utils.mathematics import rangify

_loggers = {}

class Logger:
    def __init__(self, tag: str, level: int = None): # will use global level if None
        self._tag = tag
        self._level = None
        self.set_level(level)

    def set_level(self, level: int):
        self._level = rangify(level, VERBOSITY_MIN, VERBOSITY_MAX) if level else None

    def e(self, msg, *args, **kwargs):
        self._log(VERBOSITY_ERROR, red("[ERROR] "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def w(self, msg, *args, **kwargs):
        self._log(VERBOSITY_WARNING, yellow("[WARN]  "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def i(self, msg, *args, **kwargs):
        self._log(VERBOSITY_INFO, blue("[INFO]  "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def d(self, msg, *args, **kwargs):
        self._log(VERBOSITY_DEBUG, green("[DEBUG] "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def h(self, msg, *args, **kwargs):
        self._log(VERBOSITY_HUGE, black("[HUGE] "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def x(self, tag, msg, *args, **kwargs):
        self._log(VERBOSITY_DEBUG, magenta(f"[{tag}] "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def eexception(self, msg, *args, **kwargs):
        ei = sys.exc_info()
        self.e(msg + "\n" + red("".join(traceback.format_exception(ei[0], ei[1], ei[2]))), *args, **kwargs)

    def wexception(self, msg, *args, **kwargs):
        ei = sys.exc_info()
        self.w(msg + "\n" + yellow("".join(traceback.format_exception(ei[0], ei[1], ei[2]))), *args, **kwargs)


    def _log(self, level, prefix, lineno, msg, *args, **kwargs):
        # Use overriden level or default one if not provided
        lv = self._level if self._level else get_setting(Settings.VERBOSITY)
        if lv < level:
            return

        if lineno is not None:
            print(prefix + "{" + self._tag + f":{lineno}" + "}", msg, *args, **kwargs)
        else:
            print(prefix + "{" + self._tag + "}", msg, *args, **kwargs)


def get_logger(tag: str):
    if tag not in _loggers:
        _loggers[tag] = Logger(tag)

    return _loggers[tag]


if __name__ == "__main__":
    easyshare_setup(4)
    log = get_logger("easyshare.es")
    log.e("Something went wrong!")