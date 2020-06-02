from typing import List, Optional, Callable

from easyshare.args import Option, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, \
    ArgsSpec
from easyshare.helps import CommandHelp, CommandOptionInfo



_AVAILABLE_COMMANDS_STR = """\
<I+4>
                    <A>
help                show this help
exit, quit, q       exit from the interactive shell
trace, t            enable/disable packet tracing
verbose, v          change verbosity level
</i>
<I+4>
scan, s             scan the network for easyshare servers
connect, c          connect to a remote server
disconnect          disconnect from a remote server
open, o             open a remote sharing (eventually discovering it)
close               close the remote sharing
</i>
<I+4>
get, g              get files and directories from the remote sharing
put, p              put files and directories in the remote sharing
</i>
<I+4>
pwd                 show the name of current local working directory
ls                  list local directory content
l                   alias for ls -la
tree                list local directory contents in a tree-like format
cd                  change local working directory
mkdir               create a local directory
cp                  copy files and directories locally
mv                  move files and directories locally
rm                  remove files and directories locally
find                search for local files
exec, :             execute an arbitrary command locally
shell, sh           start a local shell
</i>
<I+4>
rpwd                show the name of current remote working directory
rls                 list remote directory content
rl                  alias for rls -la
rtree               list remote directory contents in a tree-like format
rcd                 change remote working directory
rmkdir              create a remote directory
rcp                 copy files and directories remotely
rmv                 move files and directories remotely
rrm                 remove files and directories remotely
rfind               search for local files
rexec, ::           execute an arbitrary command remotely
rshell, rsh         start a remote shell
</i>
<I+4>
info, i             show information about the remote server
list                list the sharings of the remote server
ping                test the connection with the remote server</i></a>"""

USAGE = f"""\
Type <b>es<b> <u>--help</u> for see <b>es</b> usage and options.
Type <b>help <u>command</u> for the full documentation of a <u>command</u>.

Available commands are:     
                    <a>
{_AVAILABLE_COMMANDS_STR}"""


class Es(CommandHelp, ArgsSpec):

    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    DISCOVER_PORT = ["-d", "--discover-port"]
    DISCOVER_TIMEOUT = ["-w", "--discover-wait"]

    VERBOSE = ["-v", "--verbose"]
    TRACE = ["-t", "--trace"]

    NO_COLOR = ["--no-color"]

    def options_spec(self) -> Optional[List[Option]]:
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
        return lambda argname, argtype, idx, args, positionals: argtype != ArgType.POSITIONAL

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.HELP, "show this help"),
            CommandOptionInfo(cls.VERSION, "show the easyshare version"),
            CommandOptionInfo(cls.DISCOVER_PORT, "port used for broadcast discovery messages", params=["port"]),
            CommandOptionInfo(cls.DISCOVER_TIMEOUT, "time to wait for discovery responses", params=["seconds"]),
            CommandOptionInfo(cls.VERBOSE, "set verbosity level", params=["level"]),
            CommandOptionInfo(cls.TRACE, "enable/disable tracing", params=["0_or_1"]),
            CommandOptionInfo(cls.NO_COLOR, "don't print ANSI escape characters")
        ]

    @classmethod
    def name(cls):
        return "es"

    @classmethod
    def short_description(cls):
        return "client of the easyshare application"

    @classmethod
    def synopsis(cls):
        return f"""\
es <A> # just for alignment
<b>es</b> [<u>OPTION</u>]... [<u>COMMAND</u> [<u>COMMAND_OPTIONS</u>]]</a>"""

    @classmethod
    def see_also(cls):
        return "SEE THE MAN PAGE FOR MORE INFO AND EXAMPLES"

    @classmethod
    def long_description(cls):
        return f"""\
Client of the easyshare network application.

If no <b>COMMAND</b> is given, the interactive console is started.
If <b>COMMAND</b> is a valid command, it is executed and the process quits \
unless the command is <b>open</b>.

Type "<b>help <u>command</u>" for the full documentation of a <u>command</u>.

Commands:
{_AVAILABLE_COMMANDS_STR}"""

    @classmethod
    def examples(cls):
        return """\
Usage example:
   <a>
1. Start the interactive shell (from which you can use any command)</a>
<b>es</b>
   <a>
2. Scan the network for easyshare sharings</a>
<b>es</b> <u>scan</u>
<b>alice-arch (192.168.1.105:12020)</b>
  DIRECTORIES
  - shared
  - tmp
   <a>
3. Get the content of a known sharing</a>
<b>es</b> <u>get shared</u>
GET shared/f1    [===================] 100%  745KB/745KB
GET outcome: OK
Files        1  (745KB)
Time         1s
Avg. speed   1MB/s"""