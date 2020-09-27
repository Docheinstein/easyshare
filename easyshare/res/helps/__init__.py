from typing import Optional, Dict, Union

from hmd import HMD, text_filter, ansi_filter

from easyshare.common import EASYSHARE_RESOURCES_PKG
from easyshare.logging import get_logger
from easyshare.settings import get_setting, Settings
from easyshare.utils.resources import read_resource_string

_help_map: Optional[Dict[str, str]] = None
_usage_map: Optional[Dict[str, str]] = None

log = get_logger(__name__)


def command_usage(cmd: str) -> bool:
    hmd_content = _load_command_content(cmd)

    if not hmd_content:
        return False

    print(HMD(hmd_filter=text_filter).convert(hmd_content))

    return True


def command_man(cmd: Union[str, None]) -> bool:
    hmd_content = _load_command_content(cmd)

    if not hmd_content:
        return False

    HMD(hmd_filter=ansi_filter if get_setting(Settings.COLORS) else text_filter).render(hmd_content)

    return True


def _load_command_content(cmd: str) -> Optional[str]:
    try:
        return read_resource_string(EASYSHARE_RESOURCES_PKG,
                                    f"helps/{cmd}.hmd")
    except Exception:
        log.eexception(f"Exception occurred while {cmd} help")
        return None
