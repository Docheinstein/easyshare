from typing import Optional, Dict, Union

from hmd import HMD, text_filter, ansii_filter

from easyshare.common import EASYSHARE_RESOURCES_PKG
from easyshare.logging import get_logger
from easyshare.styling import is_styling_enabled
from easyshare.utils.resources import read_resource_string

_help_map: Optional[Dict[str, str]] = None
_usage_map: Optional[Dict[str, str]] = None

log = get_logger(__name__)


def command_usage(cmd: str) -> Optional[str]:
    hmd_content = _load_command_content(cmd)

    if not hmd_content:
        print(f"Can't provide help for command '{cmd}'")
        return None

    print(HMD(hmd_filter=text_filter).convert(hmd_content))


def command_man(cmd: Union[str, None]) -> Optional[str]:
    hmd_content = _load_command_content(cmd)

    if not hmd_content:
        print(f"Can't provide help for command '{cmd}'")
        return None

    HMD(hmd_filter=ansii_filter if is_styling_enabled() else text_filter).render(hmd_content)


def _load_command_content(cmd: str) -> Optional[str]:
    try:
        return read_resource_string(EASYSHARE_RESOURCES_PKG,
                                    f"helps/{cmd}.hmd")
    except Exception:
        log.exception(f"Exception occurred while {cmd} help")
        return None
