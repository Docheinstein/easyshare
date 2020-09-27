import sys
import traceback

from easyshare.common import easyshare_setup, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO
from easyshare.settings import get_setting, Settings
from easyshare.styling import yellow, red, green, blue

# TODO: convert %s to format string

class Logger:
    def __init__(self, tag: str):
        self.tag = tag

    def e(self, msg, *args, **kwargs):
        self._log(VERBOSITY_ERROR, red("[ERROR] "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def w(self, msg, *args, **kwargs):
        self._log(VERBOSITY_WARNING, yellow("[WARN]  "), sys._getframe(1).f_lineno,
                  msg, *args, **kwargs)

    def i(self, msg, *args, **kwargs):
        self._log(VERBOSITY_INFO, blue("[INFO]  "), None,
                  msg, *args, **kwargs)

    def d(self, msg, *args, **kwargs):
        self._log(VERBOSITY_INFO, green("[DEBUG] "), None,
                  msg, *args, **kwargs)

    def eexception(self, msg, *args, **kwargs):
        ei = sys.exc_info()
        self.e(msg + red("".join(traceback.format_exception(ei[0], ei[1], ei[2]))), *args, **kwargs)

    def wexception(self, msg, *args, **kwargs):
        ei = sys.exc_info()
        self.w(msg + yellow("".join(traceback.format_exception(ei[0], ei[1], ei[2]))), *args, **kwargs)


    def _log(self, level, prefix, lineno, msg, *args, **kwargs):
        if get_setting(Settings.VERBOSITY) < level:
            return

        if lineno is not None:
            print(prefix + "{" + self.tag + f":{sys._getframe(1).f_lineno}" + "}", msg, *args, **kwargs)
        else:
            print(prefix + "{" + self.tag + "}", msg, *args, **kwargs)


def get_logger(tag: str):
    return Logger(tag)


if __name__ == "__main__":
    easyshare_setup(4)
    log = get_logger("easyshare.es")
    log.e("Something went wrong!")