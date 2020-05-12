from typing import Type

import os
import datetime
import sys

# Add the the project directory to sys.path since this is outside
# the easyshare folder and the modules won't be seen otherwise

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)

from easyshare.utils.str import sorted_i
from easyshare.es.commands import CommandInfo, COMMANDS_INFO


USAGE = """\
See the manual page (man es) for a complete description of the commands.
Type "help <command>" for the documentation of <command>.

Available commands are:     
                        <a>
<b>General commands</b>
    help                show this help
    exit, quit, q       exit from the interactive shell
    trace, t            enable/disable packet tracing
    verbose, v          change verbosity level

<b>Connection establishment commands</b>
    scan, s             scan the network for easyshare servers
    connect             connect to a remote server
    disconnect          disconnect from a remote server
    open, o             open a remote sharing (eventually discovering it)
    close, c            close the remote sharing

<b>Transfer commands</b>
    get, g              get files and directories from the remote sharing
    put, p              put files and directories in the remote sharing

<b>Local commands</b>
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

<b>Remote commands</b>
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

<b>Server information commands</b>
    info, i             show information about the remote server
    list                list the sharings of the remote server
    ping                test the connection with the remote server"""


def generate_command_help_markdown(info: Type[CommandInfo]):
    # PARAGRAPH_JUSTIFY = 4 : hardcoded
    OPTIONS_JUSTIFY = 26
    info_custom = info.custom()

    if info_custom:
        # Custom format
        return info_custom

    # Standard help format

    # Compute optional parts
    info_options = None
    info_synopsis_extra = info.synopsis_extra()
    info_examples = info.examples()

    options = info.options()
    if options:
        options_strings = []
        for opt in options:
            aliases = opt.aliases_string()
            params = opt.params_string()
            options_strings.append(opt._to_string(
                aliases=aliases or "",
                param=f"<u>{params}</u>" if params else "",
                description=opt.description,
                justification=OPTIONS_JUSTIFY + (len("<u></u>") if params else 0)
            ))

        options_strings = sorted_i(options_strings)
        info_options = "\n".join(options_strings)

    info_options = ("\n" + info_options + "\n") if info_options else ""
    info_synopsis_extra = ("\n" + info_synopsis_extra + "\n") if info_synopsis_extra else ""

    s = f"""\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
{info.name()} - {info.short_description()}
</I4>

<b>SYNOPSIS</b>
<I4>
{info.synopsis()}
{info_synopsis_extra}\
</I4>

<b>DESCRIPTION</b>
<I4>
{info.long_description()}
{' ' * (OPTIONS_JUSTIFY + 4)}<A> # options alignment (34 = 4 + 30)
{info_options}\
</I4>
    <A> # paragraph alignment (4)
"""

    if info_examples:
        s += f"""
<b>EXAMPLES</b>
<I4>
{info_examples}\
</I4>"""

    return s

#
#
# #     s = f"""\
# #     <A> # alignment
# # <b>COMMAND</b>
# # <I4>
# # {info.name()} - {info.short_description()}
# # </I4>
#
# <b>SYNOPSIS</b>
# <I4>
# {info.synopsis()}
# </I4>"""
#
#     synopsis_extra = info.synopsis_extra()
#     if synopsis_extra:
#         s += """
# sy
# """
#     s += """\
# <b>DESCRIPTION</b>
# <I4>
# {info.long_description()}
# </I4>"""
#     # -- END BASE FORMAT --
#
#     # -- OPTIONS --
#     options = info.options()
#     if options:
#         options_strings = []
#         for option in info.options():
#             aliases, option_desc = option
#             options_strings.append("{}{}".format(", ".join(aliases).ljust(24), option_desc))
#
#         options_strings = sorted_i(options_strings)
#         options_string = "\n".join(options_strings)
#
#         s += f"""
#
# <I4>
# {options_string}
# </I4>"""
#     # -- END OPTIONS --
#
#     # -- EXAMPLES --
#     examples = info.examples()
#     if examples:
#         s += f"""
#
# <b>EXAMPLES</b>
# <I4>
# {examples}
# </I4>"""
#
#     # -- END EXAMPLES --
#


def generate_definition(name: str, value: str):
    return "{} = \"\"\"\\\n{}\"\"\"".format(
        name.upper(), value
    )

if __name__ == "__main__":
    cmd_helps = [
        ("usage", USAGE) # special - not actually a command
    ]
    cmd_helps += [(cmd_name, generate_command_help_markdown(cmd_info))
                 for cmd_name, cmd_info in COMMANDS_INFO.items()]

    cmd_helps_defs = [generate_definition(cmd_name, cmd_md)
                      for cmd_name, cmd_md in cmd_helps]

    print("# Automatically generated from {} on date {}".format(
        __file__,
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
        end="\n\n"
    )

    for cmd_help_def in cmd_helps_defs:
        print(cmd_help_def, end="\n\n")
        print("# ============================================================", end="\n\n")
