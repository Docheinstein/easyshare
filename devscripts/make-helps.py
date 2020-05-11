from typing import Type

import os
import datetime
import sys

# Add the the project directory to sys.path since this is outside
# the easyshare folder and the modules won't be seen otherwise
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)


from easyshare.es.commands import CommandInfo, COMMANDS_INFO


HELP = """\
See the manual page (man es) for a complete description of the commands.
Type "help <command>" for the documentation of <command>.

Available commands are:     
                        <a>
General commands
    help                show this help
    exit, quit, q       exit from the shell
    trace, t            enable/disable packet tracing
    verbose, v          change verbosity level

Connection establishment commands
    scan, s             scan the network for easyshare servers
    connect             connect to a remote server
    disconnect          disconnect from a remote server
    open, o             open a remote sharing (eventually discovering it)
    close, c            close the remote sharing

Transfer commands
    get, g              get files and directories from the remote sharing
    put, p              put files and directories in the remote sharing

Local commands
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

Remote commands
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

Server information commands
    info, i             show information about the remote server
    list                list the sharings of the remote server
    ping                test the connection with the remote server"""


def generate_command_help_markdown(info: Type[CommandInfo]):
    options_strings = []
    for option in info.options():
        aliases, option_desc = option
        options_strings.append("    {}{}".format(", ".join(aliases).ljust(24), option_desc))

    options_strings = sorted(options_strings, key=lambda opt_str: opt_str[0][0])
    options_string = "\n".join(options_strings)

    s = f"""\
    <A> # alignment
<b>COMMAND</b>
    {info.name()} - {info.short_description()}

    {info.long_description()}

<b>SYNOPSIS</b>
    {info.name()}  {info.synopsis()}

<b>OPTIONS</b>
{options_string}"""

    return s


def generate_definition(name: str, value: str):
    return "{} = \"\"\"\\\n{}\"\"\"".format(
        name.upper(), value
    )

if __name__ == "__main__":
    cmd_helps = [
        ("help", HELP) # custom
    ]
    cmd_helps += [(cmd_name, generate_command_help_markdown(cmd_info))
                 for cmd_name, cmd_info in COMMANDS_INFO.items()]

    cmd_helps_defs = [generate_definition(cmd_name, cmd_md)
                      for cmd_name, cmd_md in cmd_helps]

    print("# Automatically generated {}".format(
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
        end="\n\n"
    )

    for cmd_help_def in cmd_helps_defs:
        print(cmd_help_def, end="\n\n")
        print("# ============================================================", end="\n\n")
