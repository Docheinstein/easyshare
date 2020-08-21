from typing import List, Optional, Callable

from easyshare.args import Option, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, \
    ArgsSpec
from easyshare.commands import CommandHelp, CommandOptionInfo

_AVAILABLE_COMMANDS_STR = """\
.A                  .
help                show this help
exit, quit          exit from the interactive shell
trace               enable/disable packet tracing
verbose             change verbosity level

scan                scan the network for easyshare servers
connect             connect to a remote server
disconnect          disconnect from a remote server
open                open a remote sharing (eventually discovering it)
close               close the remote sharing

get                 get files and directories from the remote sharing
put                 put files and directories in the remote sharing

pwd                 show the name of current local working directory
ls                  list local directory content
tree                list local directory contents in a tree-like format
cd                  change local working directory
mkdir               create a local directory
cp                  copy files and directories locally
mv                  move files and directories locally
rm                  remove files and directories locally
find                search for local files
exec                execute an arbitrary command locally
shell               start a local shell

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
rexec               execute an arbitrary command remotely
rshell              start a remote shell

info                show information about the remote server
list                list the sharings of the remote server
ping                test the connection with the remote server"""

USAGE = f"""\
Type **es** *--help* for see **es** usage and options.
Type **help** *command* for the full documentation of a *command*.

Available commands are:

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
es [*OPTION*]... [*COMMAND* [*COMMAND_OPTIONS*]]\
"""

    @classmethod
    def see_also(cls):
        return "SEE THE MAN PAGE FOR MORE INFO AND EXAMPLES"

    @classmethod
    def long_description(cls):
        return f"""\
**easyshare** is a client-server command line application written in \
Python for transfer files between network hosts.

**es** is the client of the easyshare network application.

If no *COMMAND* is given, the interactive console is started. \
If *COMMAND* is a valid command, it is executed and the process quits \
unless the command is open.

**es** reads ~/.esrc file from the home directory at startup, in which \
some configuration, such as the startup parameter and aliases, can be specified.

Configuration file example (.esrc):
    # discover_port=12019
    # verbose=2
    alias l=ls -la
    alias rl=rls -la
    alias s=scan
    alias :=exec
    alias ::=rexec
    alias touch=: touch
    alias cat=: cat
    alias echo=: echo

Type "**help** *command*" for the full documentation of a command.

Commands:
{_AVAILABLE_COMMANDS_STR}"""

    @classmethod
    def examples(cls):
        return """\
These are only examples, see the *help* section of each command for known exactly
what you can do.

.A.
- Start the interactive shell (from which you can use any command)
    **es**
./A

.A.
- Scan the network for easyshare sharings
    **es** *scan*
./A
    alice-arch (192.168.1.105:12020)
      DIRECTORIES
      - shared
      - tmp

.A.
- Open a sharing by name (implicit discovery and server connection) and \
start the interactive shell
./A
    **es** *open* *shared*

    alice-arch.shared:/ - /tmp>

.A.
- Get the content of a sharing by name
./A
    **es** *get* *shared*

    GET shared/f1    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s

.A.
- Open a sharing by name and put some files into it
./A
    **es**

    /tmp> open shared
    alice-arch.shared:/ - /tmp> rls
    f1      f2
    alice-arch.shared:/ - /tmp> put /tmp/afile
    PUT afile    [===================] 100%  745KB/745KB
    PUT outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    alice-arch.shared:/ - /tmp> rls
    f1      f2      afile

.A.
- Connect to a server by specific address and port, then list the available sharings
./A
    **es** *connect* *192.168.1.105:12020*

    alice-arch:/ - /tmp> list
    DIRECTORIES
    - shared
    - tmp
    FILES
    - zshrc

.A.
- See content of the remote sharing, then move some files
./A
    **es**

    /tmp> open shared
    alice-arch.shared:/ - /tmp> rtree
    /tmp> tree
    |-- dir
    |   |-- f3
    |   +-- f4
    |-- f1
    +-- f2
    alice-arch.shared:/ - /tmp> rmv f1 f2 dir
    alice-arch.shared:/ - /tmp> rtree
    +-- dir
        |-- f1
        |-- f2
        |-- f3
        +-- f4
    alice-arch.shared:/ - /tmp> rcd dir
    alice-arch.shared:/dir - /tmp> rls
    f1      f2      f3      f4

.A.
- Arbitrary local command execution
./A.
    **es**

    >/tmp> cd d
    /tmp/d> ls
    f0
    /tmp> :touch f1
    f0      f1

.A.
- Arbitrary remote command execution (DISABLED BY DEFAULT)
./A
    **es**

    /tmp> connect alice-arch
    alice-arch:/ - /tmp> ::whoami
    alice"""