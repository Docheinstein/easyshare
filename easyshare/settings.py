from typing import Any, Dict, Callable, List, Tuple, Union, Optional, Type

from easyshare.logging import get_logger
from easyshare.utils.obj import values
from easyshare.utils.types import is_int, to_int, to_str, to_type

log = get_logger(__name__)

_settings: Dict[str, str] = {}
_settings_callbacks: List[Tuple[Callable, List[str], Type]] = [] # list of (callback, keys_filter, cast)

class Settings:
    VERBOSE = "verbose"
    TRACE = "trace"
    DISCOVER_PORT = "discover_port"
    DISCOVER_WAIT = "discover_wait"
    SHELL_PASSTHROUGH = "shell_passthrough"
    COLORS = "colors"

SETTINGS = values(Settings)

SettingChangedCallback = Callable[[str, str], None]
SettingValue = Union[str, int, float, bool]

def set_setting(key: str, value: SettingValue) -> bool:
   global _settings

   if key in SETTINGS:
       _settings[key] = value
       _notify_setting_changed(key, value) # eventually notify the callback
       return True

   return False

def get_setting(key: str, cast: Type, default=None) -> Optional[SettingValue]:
    val = _settings.get(key, None)
    if val is None:
        return default
    if not cast:
        return val

    return to_type(val, cast, default=default)


def get_setting_float(key: str, default=None) -> Optional[int]:
    return get_setting(key, cast=float, default=default)

def get_setting_int(key: str, default=None) -> Optional[int]:
    return get_setting(key, cast=int, default=default)

def get_setting_str(key: str, default=None) -> Optional[int]:
    return get_setting(key, cast=str, default=default)

def get_setting_bool(key: str, default=None) -> Optional[int]:
    return get_setting(key, cast=bool, default=default)


def add_setting_changed_callback(callback: SettingChangedCallback, keys_filter=None, cast: Type=None):
    _settings_callbacks.append((callback, keys_filter, cast))

def _notify_setting_changed(key: str, value: SettingValue):
    for cb, keys_filter, cast in _settings_callbacks:
        if not keys_filter or key in keys_filter:
            cb(key, to_type(value, totype=cast))