from typing import Type, Tuple, List
import sys

import os

# Add the the project directory to sys.path before load any easyshare module
# since this is outside the easyshare folder and the modules won't be
# seen otherwise

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)

from easyshare.help.esd import Esd
from easyshare.help import CommandHelp, CommandOptionHelp
from easyshare.help.es import Es
from easyshare.utils.json import j
from easyshare.utils.str import sorted_i
from easyshare.help.commands import COMMANDS_INFO
from easyshare.utils.app import eprint


def make_section(name: str, content: str, indent: int = 4, alignment: int = 0,
                 leading_endl: int = 2, trailing_endl: int = 0) -> str:

    if not name or not content:
        return ""

    # -------------
    return ("\n" * leading_endl) + f"""\
<b>{name}</b>
<I{indent}>
{' ' * alignment}<A> # alignment
{content}</a></i{indent}>""" + ("\n" * trailing_endl)
    # -------------


def generate_command_help_markdown(info: Type[CommandHelp], output_style = "man"):
    # PARAGRAPH_INDENT = 4
    OPTIONS_DESC_SPACING = 4

    info_custom = info.custom()

    if info_custom:
        # Custom format
        return info_custom

    # Standard help format

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

        def aliases_string(opt: CommandOptionHelp) -> Tuple[str, int]: # string, ansi count
            aliases_len = len(opt.aliases) if opt.aliases else 0
            open_tag = "<b>" if output_style == "man" else ""
            end_tag = "</b>" if output_style == "man" else ""
            return ", ".join(f"{open_tag}{a}{end_tag}" for a in opt.aliases) if opt.aliases else "", \
                   ((len("<b></b>") * aliases_len) if output_style == "man" else 0)

        def params_string(opt: CommandOptionHelp) -> Tuple[str, int]:
            params_len = len(opt.params) if opt.params else 0
            open_tag = "<u>" if output_style == "man" else "<"
            end_tag = "</u>" if output_style == "man" else ">"
            return " ".join(f"{open_tag}{p}{end_tag}" for p in opt.params) if opt.params else "", \
                   ((len("<u></u>") * params_len) if output_style == "man" else 0)
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
            options_strings.append(opt._to_string(
                aliases=aliases_str,
                params=params_srt,
                description=opt.description,
                justification=options_alignment + aliases_str_style_chars + params_str_style_chars)
            )

            # eprint(info.name(), " - opt", opt.aliases, opt.params, " REAL_LEN = ",
            #        options_alignment, " + ",
            #     aliases_str_style_chars, params_str_style_chars)

        options_strings = sorted_i(options_strings)
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



USAGE = """\
Type <b>es<b> <u>--help</u> for see <b>es</b> usage and options.
Type <b>help <u>command</u> for the full documentation of a <u>command</u>.

Available commands are:     
                        <a>
<b>General commands</b>
<I4>
    help                show this help
    exit, quit, q       exit from the interactive shell
    trace, t            enable/disable packet tracing
    verbose, v          change verbosity level
</i>
<b>Connection establishment commands</b>
<I4>
    scan, s             scan the network for easyshare servers
    connect             connect to a remote server
    disconnect          disconnect from a remote server
    open, o             open a remote sharing (eventually discovering it)
    close, c            close the remote sharing
</i>
<b>Transfer commands</b>
<I4>
    get, g              get files and directories from the remote sharing
    put, p              put files and directories in the remote sharing
</i>
<b>Local commands</b>
<I4>
    pwd                 show the name of current local working directory
    ls                  list local directory content
    l                   alias for ls -la
    tree                list local directory contents in a tree-like format
    cd                  change local working directory
    mkdir               create a local directory
    cp                  copy files and directories locally
    mv                  move files and directories locally
    rm                  remove files and directories locally
    exec, :             execute an arbitrary command locally
</i>
<b>Remote commands</b>
<I4>
    rpwd                show the name of current remote working directory
    rls                 list remote directory content
    rl                  alias for rls -la
    rtree               list remote directory contents in a tree-like format
    rcd                 change remote working directory
    rmkdir              create a remote directory
    rcp                 copy files and directories remotely
    rmv                 move files and directories remotely
    rrm                 remove files and directories remotely
    rexec, ::           execute an arbitrary command remotely (disabled by default) since it will compromise server security
</i>
<b>Server information commands</b>
<I4>
    info, i             show information about the remote server
    list                list the sharings of the remote server
    ping                test the connection with the remote server</i></a>"""



if __name__ == "__main__":
    style = "man"
    if len(sys.argv) > 1:
        if sys.argv[1] == "man" or sys.argv[1] == "usage":
            style = sys.argv[1]

    eprint(f"Generating '{style}' help")

    cmds: List[Tuple[str, Type[CommandHelp]]] = \
        list(COMMANDS_INFO.items()) + [(Es.name(), Es), (Esd.name(), Esd)]

    cmd_helps_str = [(cmd_name, generate_command_help_markdown(cmd_help, style))
                      for cmd_name, cmd_help in cmds] + [
        ("usage", USAGE) # special - not actually a command
    ]

    print(j({cmd_name: cmd_help_str for cmd_name, cmd_help_str in cmd_helps_str}))
