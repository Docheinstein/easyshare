from typing import Dict, Callable, List, Tuple, Union, Optional

from easyshare.common import TRACING_MIN, TRACING_MAX, VERBOSITY_MIN, VERBOSITY_MAX
from easyshare.utils.mathematics import rangify
from easyshare.utils.obj import values
from easyshare.utils.types import to_int, to_float, to_bool


def _to_port(o):
    p = to_int(o)
    if 0 <= p <= 65535:
        return p
    raise ValueError("Invalid port number")

SettingValue = Union[str, int, float, bool]
SettingChangedCallback = Callable[[str, str], None]

class Settings:
    VERBOSITY = "verbose"
    TRACING = "trace"
    DISCOVER_PORT = "discover_port"
    DISCOVER_WAIT = "discover_wait"
    SHELL_PASSTHROUGH = "shell_passthrough"
    COLORS = "colors"

SETTINGS = values(Settings)

_settings_values: Dict[str, SettingValue] = {}
_settings_callbacks: List[Tuple[Callable, List[str]]] = [] # list of (callback, keys_filter, cast)

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
        raise ValueError(f"Unknown key: {key}")

    try:
        _settings_values[key] = parser(value)
        _notify_setting_changed(key, _settings_values[key])  # eventually notify the callbacks
    except Exception:
        raise ValueError(f"Invalid value: {value}")

def get_setting(key: str, default=None) -> Optional[SettingValue]:
    return _settings_values.get(key, default)

def add_setting_callback(key_filter: str, callback: SettingChangedCallback):
    add_settings_callback(callback, [key_filter])

def add_settings_callback(callback: SettingChangedCallback, keys_filter=None):
    _settings_callbacks.append((callback, keys_filter))

def _notify_setting_changed(key: str, value: SettingValue):
    for cb, keys_filter in _settings_callbacks:
        if not keys_filter or key in keys_filter:
            cb(key, value)