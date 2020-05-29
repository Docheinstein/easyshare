from typing import Optional, Dict, Union

from easyshare.common import EASYSHARE_RESOURCES_PKG
from easyshare.logging import get_logger
from easyshare.utils import eprint
from easyshare.utils.helpmarkdown import HelpMarkdown, HelpMarkdownParseError
from easyshare.utils.json import stoj
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
        try:
            _usage_map = stoj(
                read_resource_string(EASYSHARE_RESOURCES_PKG,
                                     "helps/usages.json"))
        except Exception:
            log.exception("Exception occurred while loading help")
            pass


    if not _usage_map:
        log.e("Failed to load usages")
        return None

    return _get_command_hmd_from_map(cmd, False, _usage_map)

def get_command_help(cmd: Union[str, None], styled: bool = True) -> Optional[str]:
    """
    Returns the help markdown of the help of a command (more information)
    """
    global _help_map

    if not _help_map:
        log.i("Loading help map")

        try:
            _help_map = stoj(
                read_resource_string(EASYSHARE_RESOURCES_PKG,
                                     "helps/helps.json"))
        except Exception:
            log.exception("Exception occurred while loading help")
            pass


    if not _help_map:
        log.e("Failed to load help")
        return None

    return _get_command_hmd_from_map(cmd, styled, _help_map)

def _get_command_hmd_from_map(cmd: Union[str, None], styled: bool, help_map: Dict) -> Optional[str]:
    """
    Extracts the given help markdown string from the given map.
    """
    if not help_map:
        eprint("Failed to load help")
        return None

    if cmd:
        # Show the helps of cmd if found on helps.py
        # cmd_help = getattr(helps, cmd.upper(), None)
        cmd_help = help_map.get(cmd)
    else:
        cmd_help = help_map["usage"]


    if not cmd_help:
        eprint("Can't find help for command '{}'".format(cmd))
        return None

    try:
        formatted_cmd_help = HelpMarkdown(cmd_help).to_term_str(styled=styled)
    except HelpMarkdownParseError:
        log.exception("Exception occurred while parsing help markdown")
        return None

    return formatted_cmd_help.strip("\n")

