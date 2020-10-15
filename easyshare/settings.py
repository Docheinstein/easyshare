from typing import Dict, Callable, List, Tuple, Union, Optional

from easyshare.common import TRACING_MIN, TRACING_MAX, VERBOSITY_MIN, VERBOSITY_MAX, VERBOSITY_NONE, \
    DEFAULT_DISCOVER_PORT, DEFAULT_DISCOVER_WAIT, TRACING_NONE
from easyshare.utils.mathematics import rangify
from easyshare.utils.obj import values
from easyshare.utils.types import to_int, to_float, to_bool


def _to_port(o):
    p = to_int(o)
    if 0 <= p <= 65535:
        return p
    raise ValueError("Invalid port number")

SettingValue = Union[str, int, float, bool]
SettingCallback = Callable[[str, str], None]

class Settings:
    # es/esd
    VERBOSITY = "verbose"
    TRACING = "trace"
    COLORS = "colors"

    # es only
    DISCOVER_PORT = "discover_port"
    DISCOVER_WAIT = "discover_wait"
    SHELL_PASSTHROUGH = "shell_passthrough"


SETTINGS = values(Settings)

_settings_values: Dict[str, SettingValue] = {
    Settings.VERBOSITY: VERBOSITY_NONE,
    Settings.TRACING: TRACING_NONE,
    Settings.DISCOVER_PORT: DEFAULT_DISCOVER_PORT,
    Settings.DISCOVER_WAIT: DEFAULT_DISCOVER_WAIT,
    Settings.SHELL_PASSTHROUGH: False,
    Settings.COLORS: True,
}

_settings_callbacks: List[Tuple[Callable, List[str], bool]] = [] # list of (callback, keys_filter, lazy)

_SETTINGS_PARSERS: Dict[str, Callable[[SettingValue], SettingValue]] = {
    Settings.VERBOSITY: lambda o: rangify(to_int(o, raise_exceptions=True), VERBOSITY_MIN, VERBOSITY_MAX),
    Settings.TRACING: lambda o: rangify(to_int(o, raise_exceptions=True), TRACING_MIN, TRACING_MAX),
    Settings.DISCOVER_PORT: _to_port,
    Settings.DISCOVER_WAIT: lambda v: to_float(v, raise_exceptions=True),
    Settings.SHELL_PASSTHROUGH: lambda v: to_bool(v, raise_exceptions=True),
    Settings.COLORS: lambda v: to_bool(v, raise_exceptions=True),
}


def set_setting(key: str, value: SettingValue):
    global _settings_values

    parser = _SETTINGS_PARSERS.get(key)

    if not parser:
        raise ValueError(f"Unknown key: \"{key}\"")

    try:
        prev_val = _settings_values[key]
        _settings_values[key] = parser(value)
        _notify_setting_changed(key, _settings_values[key], prev_val)  # eventually notify the callbacks
    except Exception:
        raise ValueError(f"Invalid value: \"{value}\"")

def get_setting(key: str, default=None) -> Optional[SettingValue]:
    return _settings_values.get(key, default)

def add_setting_callback(key_filter: str, callback: SettingCallback, lazy: bool=True):
    add_settings_callback(callback, [key_filter], lazy)

def add_settings_callback(callback: SettingCallback, keys_filter=None, lazy: bool=True):
    _settings_callbacks.append((callback, keys_filter, lazy))

def _notify_setting_changed(key: str, value: SettingValue, prev_value: SettingValue):
    for cb, keys_filter, lazy in _settings_callbacks:
        if (not keys_filter or key in keys_filter) and \
            (not lazy or prev_value != value):
            cb(key, value)