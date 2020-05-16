from typing import List, Optional, Callable

from easyshare.args import Kwarg, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, Pargs, \
    ArgsParser
from easyshare.help import CommandHelp, CommandOptionHelp


class Es(CommandHelp, ArgsParser):
    @classmethod
    def name(cls):
        return "es"

    @classmethod
    def short_description(cls):
        return "client of the easyshare application"

    @classmethod
    def synopsis(cls):
        return f"""\
es [<u>OPTION</u>]... [<u>COMMAND</u> [<u>COMMAND_ARGUMENTS</u>]]"""

    @classmethod
    def long_description(cls):
        return """\
Client of the easyshare network application.

If no <b>COMMAND</b> is given, the interactive console is started.
If <b>COMMAND</b> is a valid command, it is executed and the process quits \
unless the command is <b>open</b>.

Type "<b>help <u>command</u>" for the full documentation of a <u>command</u>.

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

    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    DISCOVER_PORT = ["-d", "--discover-port"]
    DISCOVER_TIMEOUT = ["-w", "--discover-wait"]

    VERBOSE = ["-v", "--verbose"]
    TRACE = ["-t", "--trace"]

    NO_COLOR = ["--no-color"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.HELP, PRESENCE_PARAM),
            (self.VERSION, PRESENCE_PARAM),
            (self.DISCOVER_PORT, INT_PARAM),
            (self.DISCOVER_TIMEOUT, INT_PARAM),
            (self.VERBOSE, INT_PARAM_OPT),
            (self.TRACE, INT_PARAM_OPT),
            (self.NO_COLOR, PRESENCE_PARAM),
        ]

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, Args, List[str]], bool]]:
        return lambda argname, argtype, idx, args, positionals: argtype != ArgType.PARG

    @classmethod
    def options(cls) -> List[CommandOptionHelp]:
        return [
            CommandOptionHelp(cls.HELP, "show this help"),
            CommandOptionHelp(cls.VERSION, "show the easyshare version"),
            CommandOptionHelp(cls.DISCOVER_PORT, "port used for broadcast discovery messages"),
            CommandOptionHelp(cls.DISCOVER_TIMEOUT, "time to wait for discovery responses"),
            CommandOptionHelp(cls.VERBOSE, "set verbosity level", params=["level"]),
            CommandOptionHelp(cls.TRACE, "enable/disable tracing", params=["0_or_1"]),
            CommandOptionHelp(cls.NO_COLOR, "don't print ANSI escape characters")
        ]
