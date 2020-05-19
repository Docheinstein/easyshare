from typing import Type, Tuple, List, Optional
import sys

import os

# Add the the project directory to sys.path before load any easyshare module
# since this is outside the easyshare folder and the modules won't be
# seen otherwise

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)

# Now we can import easyshare stuff

from easyshare.helps.es import Es, USAGE
from easyshare.helps.esd import Esd
from easyshare.helps.estools import EsTools
from easyshare.helps import CommandHelp, CommandOptionInfo, CommandUsage
from easyshare.utils.json import j
from easyshare.utils.str import isorted
from easyshare.helps.commands import COMMANDS_INFO
from easyshare.utils import eprint


def make_section(name: Optional[str], content: str, *,
                 indent: int = 4, alignment: int = 0,
                 leading_endl: int = 2, trailing_endl: int = 0) -> str:

    if not content:
        return ""

    # -------------
    s = ("\n" * leading_endl)

    if name:
        s+= f"<b>{name}</b>\n"

    s += f"""\
<I{indent}>
{' ' * alignment}<A> # alignment
{content}</a></i{indent}>""" + ("\n" * trailing_endl)

    return s
    # -------------



def generate_command_usage_markdown(info: Type[CommandUsage]):
    OPTIONS_DESC_SPACING = 4

    info_options = None

    options = info.options()

    longest_aliases_w_params = 0
    options_alignment = 0

    if options:
        options_strings = []

        # TODO: refactor using ansistr

        def aliases_string(opt: CommandOptionInfo) -> str:
            return ", ".join(f"{a}" for a in opt.aliases) if opt.aliases else ""

        def params_string(opt: CommandOptionInfo) -> str:
            return " ".join(f"<{p}>" for p in opt.params) if opt.params else ""

        for opt in options:
            longest_aliases_w_params = max(
                longest_aliases_w_params,
                len(aliases_string(opt)) +
                (len(" ") if opt.params else 0) +
                len(params_string(opt))
            )

        options_alignment = longest_aliases_w_params + OPTIONS_DESC_SPACING

        for opt in options:
            options_strings.append(opt.as_string(
                aliases=aliases_string(opt),
                params=params_string(opt),
                description=opt.description,
                justification=options_alignment)
            )

        options_strings = isorted(options_strings, not_in_subset="-")
        info_options = "\n".join(options_strings)

    section_synopsis = make_section(
        None,
        f"{info.synopsis()}",
        leading_endl=0
    )

    section_trail = make_section(
        None,
        info.see_also(),
        leading_endl=2,
        indent=0
    )
    section_options = make_section(
        None,
        info_options,
        leading_endl=0,
        alignment=options_alignment
    )

    s = f"""\
Usage:
{section_synopsis}

Options:
{section_options}\
"""
    if section_trail:
        s += section_trail

    return s

def generate_command_help_markdown(info: Type[CommandHelp], styled: bool = True):
    # PARAGRAPH_INDENT = 4
    OPTIONS_DESC_SPACING = 4

    info_custom = info.custom()

    if info_custom:
        # Custom format
        return info_custom

    # Standard helps format

    # Compute optional parts
    info_synopsis_extra = info.synopsis_extra()
    info_options = None
    info_examples = info.examples()
    info_see_also = info.see_also()

    options = info.options()

    longest_aliases_w_params = 0
    options_alignment = 0

    if options:
        options_strings = []


        # TODO: refactor using ansistr

        def aliases_string(opt: CommandOptionInfo) -> Tuple[str, int]: # string, ansi count
            aliases_len = len(opt.aliases) if opt.aliases else 0
            open_tag = "<b>" if styled else ""
            end_tag = "</b>" if styled else ""
            return ", ".join(f"{open_tag}{a}{end_tag}" for a in opt.aliases) if opt.aliases else "", \
                   ((len("<b></b>") * aliases_len) if styled else 0)

        def params_string(opt: CommandOptionInfo) -> Tuple[str, int]:
            params_len = len(opt.params) if opt.params else 0
            open_tag = "<u>" if styled else "<"
            end_tag = "</u>" if styled else ">"
            return " ".join(f"{open_tag}{p}{end_tag}" for p in opt.params) if opt.params else "", \
                   ((len("<u></u>") * params_len) if styled else 0)
                    # don't keep < > into account, not ansi chars

        for opt in options:
            aliases_str, aliases_str_style_chars = aliases_string(opt)
            params_srt, params_str_style_chars = params_string(opt)

            longest_aliases_w_params = max(
                longest_aliases_w_params,
                len(aliases_str) - aliases_str_style_chars + (len(" ") if opt.params else 0) +
                len(params_srt) - params_str_style_chars
            )

            # eprint(info.name(), " - opt", opt.aliases, opt.params, " LEN = ",
            #        longest_aliases_w_params, " + ",
            #        aliases_str_style_chars, params_str_style_chars)

        options_alignment = longest_aliases_w_params + OPTIONS_DESC_SPACING

        for opt in options:
            aliases_str, aliases_str_style_chars = aliases_string(opt)
            params_srt, params_str_style_chars = params_string(opt)
            options_strings.append(opt.as_string(
                aliases=aliases_str,
                params=params_srt,
                description=opt.description,
                justification=options_alignment + aliases_str_style_chars + params_str_style_chars)
            )

            # eprint(info.name(), " - opt", opt.aliases, opt.params, " REAL_LEN = ",
            #        options_alignment, " + ",
            #     aliases_str_style_chars, params_str_style_chars)

        options_strings = isorted(options_strings, not_in_subset="-")
        info_options = "\n".join(options_strings)

    subsection_synopsis_extra = ("\n\n" + info_synopsis_extra) if info_synopsis_extra else ""

    # section_synopsis_extra = info_synopsis_extra
    section_command = make_section(
        "COMMAND", f"{info.name()} - {info.short_description()}",
        leading_endl=0
    )
    section_synopsis = make_section(
        "SYNOPSIS",
        f"{info.synopsis()}{subsection_synopsis_extra}"
    )

    section_description = make_section(
        "DESCRIPTION",
        info.long_description()
    )
    section_options = make_section(
        "OPTIONS", info_options,
        alignment=options_alignment
    )
    section_examples = make_section(
        "EXAMPLES", info_examples
    )
    section_see_also = make_section(
        "SEE ALSO",
        info_see_also
    )

    return f"""\
{section_command}\
{section_synopsis}\
{section_description}\
{section_options}\
{section_examples}\
{section_see_also}\
"""



if __name__ == "__main__":
    GENERATORS_MAPS = {
        "man": generate_command_help_markdown,
        "usage": generate_command_usage_markdown
    }
    style = "man"
    if len(sys.argv) > 1:
        if sys.argv[1] == "man" or sys.argv[1] == "usage":
            style = sys.argv[1]

    eprint(f"Generating '{style}' help")

    # noinspection PyTypeChecker
    cmds: List[Tuple[str, Type[CommandHelp]]] = \
        [(k, v) for k, v in COMMANDS_INFO.items()] + [
            (Es.name(), Es),
            (Esd.name(), Esd),
            (EsTools.name(), EsTools)
        ]

    cmd_helps_str = [(cmd_name, GENERATORS_MAPS[style](cmd_help))
                      for cmd_name, cmd_help in cmds] + [
        ("usage", USAGE) # special - not actually a command
    ]

    print(j({cmd_name: cmd_help_str for cmd_name, cmd_help_str in cmd_helps_str}))
