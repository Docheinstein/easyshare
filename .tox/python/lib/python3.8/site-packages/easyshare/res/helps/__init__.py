from typing import Optional, Dict, Union

from easyshare.common import EASYSHARE_RESOURCES_PKG
from easyshare.logging import get_logger
from easyshare.utils.app import eprint
from easyshare.utils.helpmarkdown import HelpMarkdown, HelpMarkdownParseError
from easyshare.utils.json import str_to_json
from easyshare.utils.resources import read_resource_string

_help_map: Optional[Dict[str, str]] = None
_usage_map: Optional[Dict[str, str]] = None

log = get_logger(__name__)

def get_command_usage(cmd: str) -> Optional[str]:
    """
    Returns the help markdown of the usage of a command (minimal information)
    """
    global _usage_map
    if not _usage_map:
        log.i("Loading usages map")
        _usage_map = str_to_json(read_resource_string(EASYSHARE_RESOURCES_PKG, "helps/usages.json"))

    if not _usage_map:
        eprint("Failed to load usages map")
        return None

    return _get_command_hmd_from_map(cmd, False, _usage_map)

def get_command_help(cmd: Union[str, None], styled: bool = True) -> Optional[str]:
    """
    Returns the help markdown of the help of a command (more information)
    """
    global _help_map
    if not _help_map:
        log.i("Loading help map")
        _help_map = str_to_json(read_resource_string(EASYSHARE_RESOURCES_PKG, "helps/helps.json"))

    if not _help_map:
        eprint("Failed to load help map")
        return None

    return _get_command_hmd_from_map(cmd, styled, _help_map)

def _get_command_hmd_from_map(cmd: Union[str, None], styled: bool, help_map: Dict) -> Optional[str]:
    """
    Extract the given help markdown string from the given map.
    """
    if not help_map:
        eprint("Failed to load helps")
        return None

    if cmd:
        # Show the helps of cmd if found on helps.py
        # cmd_help = getattr(helps, cmd.upper(), None)
        cmd_help = help_map.get(cmd)
    else:
        cmd_help = help_map["usage"]


    if not cmd_help:
        eprint("Can't find helps for command '{}'".format(cmd))
        return None

    try:
        formatted_cmd_help = HelpMarkdown(cmd_help).to_term_str(styled=styled)
    except HelpMarkdownParseError:
        log.exception("Exception occurred while parsing markdown of helps")
        eprint("Can't provide helps for command '{}'".format(cmd))
        return None

    return formatted_cmd_help.strip("\n")

