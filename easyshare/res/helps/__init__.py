from typing import Optional, Dict, Union

from easyshare.common import RESOURCES_PKG
from easyshare.logging import get_logger
from easyshare.utils.app import eprint
from easyshare.utils.hmd import HelpMarkdown, HelpMarkdownParseError
from easyshare.utils.json import str_to_json
from easyshare.utils.resources import read_resource_string

_man_map: Optional[Dict[str, str]] = None
_usage_map: Optional[Dict[str, str]] = None

log = get_logger(__name__)

def get_command_usage(cmd: str) -> Optional[str]:
    global _usage_map
    if not _usage_map:
        log.i("Loading usages map")
        _usage_map = str_to_json(read_resource_string(RESOURCES_PKG, "helps/usages.json"))

    if not _usage_map:
        eprint("Failed to load usages map")
        return None

    return _get_command_help(cmd, False, _usage_map)

def get_command_man(cmd: Union[str, None], styled: bool = True) -> Optional[str]:
    global _man_map
    if not _man_map:
        log.i("Loading manuals map")
        _man_map = str_to_json(read_resource_string(RESOURCES_PKG, "helps/mans.json"))

    if not _man_map:
        eprint("Failed to load manuals map")
        return None

    return _get_command_help(cmd, styled, _man_map)

def _get_command_help(cmd: Union[str, None], styled: bool, help_map: Dict):
    if not help_map:
        eprint("Failed to load help")
        return None

    if cmd:
        # Show the help of cmd if found on help.py
        # cmd_help = getattr(help, cmd.upper(), None)
        cmd_help = help_map.get(cmd)
    else:
        cmd_help = help_map["usage"]


    if not cmd_help:
        eprint("Can't find help for command '{}'".format(cmd))
        return None

    try:
        formatted_cmd_help = HelpMarkdown(cmd_help).to_term_str(styled=styled)
    except HelpMarkdownParseError:
        log.exception("Exception occurred while parsing markdown of help")
        eprint("Can't provide help for command '{}'".format(cmd))
        return None

    return formatted_cmd_help.strip("\n")

