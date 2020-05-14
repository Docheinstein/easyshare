import os
from abc import abstractmethod, ABC
from typing import List, Callable, Union, Optional, Dict, Type

from easyshare.args import Kwarg, PRESENCE_PARAM, INT_PARAM, NoPargs, Pargs
from easyshare.es.ui import StyledString
from easyshare.logging import get_logger
from easyshare.protocol import FileInfo
from easyshare.protocol import FTYPE_DIR, FTYPE_FILE
from easyshare.protocol import is_data_response
from easyshare.common import DIR_COLOR, FILE_COLOR
from easyshare.styling import fg
from easyshare.utils.os import ls
from easyshare.utils.str import rightof

log = get_logger(__name__)


# =============================================
# =============== COMMANDS ====================
# =============================================

SPECIAL_COMMAND_MARK = ":"

class Commands:
    HELP = "help"
    HELP_SHORT = "h"
    EXIT = "exit"
    QUIT = "quit"
    QUIT_SHORT = "q"

    TRACE = "trace"
    TRACE_SHORT = "t"

    VERBOSE = "verbose"
    VERBOSE_SHORT = "v"

    LOCAL_CURRENT_DIRECTORY = "pwd"
    LOCAL_LIST_DIRECTORY = "ls"
    LOCAL_LIST_DIRECTORY_ENHANCED = "l"
    LOCAL_TREE_DIRECTORY = "tree"
    LOCAL_CHANGE_DIRECTORY = "cd"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_COPY = "cp"
    LOCAL_MOVE = "mv"
    LOCAL_REMOVE = "rm"
    LOCAL_EXEC = "exec"
    LOCAL_EXEC_SHORT = SPECIAL_COMMAND_MARK

    REMOTE_CURRENT_DIRECTORY = "rpwd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_LIST_DIRECTORY_ENHANCED = "rl"
    REMOTE_TREE_DIRECTORY = "rtree"
    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_COPY = "rcp"
    REMOTE_MOVE = "rmv"
    REMOTE_REMOVE = "rrm"
    REMOTE_EXEC = "rexec"
    REMOTE_EXEC_SHORT = SPECIAL_COMMAND_MARK * 2

    SCAN = "scan"
    SCAN_SHORT = "s"

    CONNECT = "connect"
    DISCONNECT = "disconnect"

    OPEN = "open"
    OPEN_SHORT = "o"
    CLOSE = "close"
    CLOSE_SHORT = "c"

    GET = "get"
    GET_SHORT = "g"
    PUT = "put"
    PUT_SHORT = "p"

    LIST = "list"
    INFO = "info"
    INFO_SHORT = "i"
    PING = "ping"


def is_special_command(s: str):
    return s.startswith(SPECIAL_COMMAND_MARK)

def matches_special_command(s: str, sp_comm: str):

    return is_special_command(sp_comm) and \
           s.startswith(sp_comm) and \
           (len(s) == len(sp_comm) or s[len(sp_comm)] != SPECIAL_COMMAND_MARK)


# ==================================================
# ============ BASE COMMAND INFO ===================
# ==================================================

class SuggestionsIntent:
    def __init__(self,
                 suggestions: List[StyledString],
                 *,
                 completion: bool = True,
                 space_after_completion: Union[Callable[[str], bool], bool] = True,
                 max_columns: int = None,
                 ):
        self.suggestions: List[StyledString] = suggestions
        self.completion: bool = completion
        self.space_after_completion: Union[Callable[[str], bool], bool] = space_after_completion
        self.max_columns: int = max_columns

    def __str__(self):
        return "".join([str(s) for s in self.suggestions])

# CommandOptionInfo = Tuple[List[str], str]

class CommandOptionInfo:
    def __init__(self, aliases: Optional[List[str]], description: str, params: Optional[List[str]] = None):
        self.aliases = aliases
        self.description = description
        self.params = params

    def aliases_string(self) -> str:
        if not self.aliases:
            return ''
        return ', '.join(self.aliases)

    def params_string(self) -> str:
        if not self.params:
            return ''
        return ' '.join(self.params)

    def to_string(self, justification: int = 0):
        return CommandOptionInfo._to_string(
            self.aliases_string(),
            self.params_string(),
            self.description,
            justification
        )

    @staticmethod
    def _to_string(aliases: str, param: str, description: str, justification: int):
        return f"{(aliases + ' ' + param).ljust(justification)}{description}"

class CommandInfo(ABC):
    @classmethod
    @abstractmethod
    def name(cls):
        pass

    @classmethod
    @abstractmethod
    def short_description(cls):
        pass

    @classmethod
    @abstractmethod
    def synopsis(cls):
        pass

    @classmethod
    def synopsis_extra(cls):
        return None

    @classmethod
    @abstractmethod
    def long_description(cls):
        pass

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return []

    @classmethod
    def examples(cls):
        return []

    @classmethod
    def see_also(cls):
        return None

    @classmethod
    def custom(cls):
        return None

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        options = cls.options()

        if not options:
            log.d("No options to suggest")
            return None

        log.i("Token: %s", token)
        if not token.startswith("-"):
            # This class handles only the kwargs ('-', '--')
            # The sub classes can provide something else
            return None

        log.d("Computing (%d) args suggestions", len(options))

        longest_option_length = max(
            [len(o.aliases_string()) + len(" ") + len(o.params_string()) for o in options]
        )

        log.d("longest_option string length: %d", longest_option_length)

        suggestions = []

        # TODO param

        for opt in options:
            suggestions.append(StyledString(
                opt.to_string(justification=longest_option_length + 6)
            ))

        return SuggestionsIntent(suggestions,
                                 completion=False,
                                 max_columns=1)


# ==================================================
# ============== LIST COMMAND INFO =================
# ==================================================

class ListCommandInfo(CommandInfo, ABC):
    @classmethod
    @abstractmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        pass

    @classmethod
    @abstractmethod
    def list(cls, token: str, line: str, client) -> List[FileInfo]:
        pass

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        log.d("Providing files listing suggestions")

        suggestions_intent = super().suggestions(token, line, client)
        if suggestions_intent:
            return suggestions_intent

        suggestions = []
        for finfo in cls.list(token, line, client):
            log.d("Suggestion finfo: %s", finfo)

            fname = finfo.get("name")

            if not cls.display_path_filter(finfo):
                log.d("%s doesn't pass the filter", fname)
                continue

            _, fname_tail = os.path.split(fname)

            if not fname_tail.lower().startswith(token.lower()):
                continue

            if finfo.get("ftype") == FTYPE_DIR:
                # Append a dir, with a trailing / so that the next
                # suggestion can continue to traverse the file system
                ff = fname_tail + "/"
                suggestions.append(StyledString(ff, fg(ff, color=DIR_COLOR)))
            else:
                # Append a file, with a trailing space since there
                # is no need to traverse the file system
                ff = fname_tail
                suggestions.append(StyledString(ff, fg(ff, color=FILE_COLOR)))

        return SuggestionsIntent(suggestions,
                                 completion=True,
                                 space_after_completion=lambda s: not s.endswith("/"))


class ListLocalCommandInfo(ListCommandInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client) -> List[FileInfo]:
        log.i("List on token = '%s', line = '%s'", token, line)
        pattern = rightof(line, " ", from_end=True)
        path_dir, path_trail = os.path.split(os.path.join(os.getcwd(), pattern))
        log.i("ls-ing on %s", path_dir)
        return ls(path_dir)


class ListRemoteCommandInfo(ListCommandInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client) -> List[FileInfo]:
        if not client or not client.is_connected_to_sharing():
            log.w("Cannot list suggestions on a non connected es")
            return []

        log.i("List remotely on token = '%s', line = '%s'", token, line)
        pattern = rightof(line, " ", from_end=True)
        path_dir, path_trail = os.path.split(pattern)

        log.i("rls-ing on %s", pattern)
        resp = client.sharing_connection.rls(sort_by=["name"], path=path_dir)

        if not is_data_response(resp):
            log.w("Unable to retrieve a valid response for rls")
            return []

        return resp.get("data")



# ==================================================
# ================== LIST FILTERS ==================
# ==================================================

class ListAllFilter(ListCommandInfo, ABC):
    @classmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        return True


class ListDirsFilter(ListCommandInfo, ABC):
    @classmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        return finfo.get("ftype") == FTYPE_DIR


class ListFilesFilter(ListCommandInfo, ABC):
    @classmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        return finfo.get("ftype") == FTYPE_FILE


class ListLocalAllCommandInfo(ListLocalCommandInfo, ListAllFilter, ABC):
    pass


class ListLocalDirsCommandInfo(ListLocalCommandInfo, ListDirsFilter, ABC):
    pass


class ListLocalFilesCommandInfo(ListLocalCommandInfo, ListFilesFilter, ABC):
    pass


class ListRemoteAllCommandInfo(ListRemoteCommandInfo, ListAllFilter, ABC):
    pass


class ListRemoteDirsCommandInfo(ListRemoteCommandInfo, ListDirsFilter, ABC):
    pass


class ListRemoteFilesCommandInfo(ListRemoteCommandInfo, ListFilesFilter, ABC):
    pass


# ==================================================
# ============== COMMON DESCRIPTIONS ===============
# ==================================================


class FastSharingConnectionCommandInfo(CommandInfo, ABC):
    @classmethod
    def synopsis_extra(cls):
        return """\
<u>SHARING_LOCATION</u> must be specified if and only if not already \
connected to a remote sharing. In that case the connection will be \
established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format."""

class FastServerConnectionCommandInfo(CommandInfo, ABC):
    @classmethod
    def synopsis_extra(cls):
        return """\
<u>SERVER_LOCATION</u> must be specified if and only if not already \
connected to a remote server. In that case the connection will be \
established before execute the command, as "<b>connect</b> <u>SERVER_LOCATION</u>" would do.

Type "<b>help connect</b>" for more information about <u>SERVER_LOCATION</u> format."""

# ==================================================
# ========== REAL COMMANDS INFO IMPL ===============
# ==================================================

# ============ HELP ================

class Help(CommandInfo):

    @classmethod
    def name(cls):
        return "help"

    @classmethod
    def short_description(cls):
        return "show the help of a command"

    @classmethod
    def synopsis(cls):
        return "<b>help</b> [<u>COMMAND</u>]"

    @classmethod
    def long_description(cls):
        comms = "\n".join(["    " + comm for comm in sorted(COMMANDS_INFO.keys())])
        return f"""\
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
{comms}"""

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        log.d("Providing commands suggestions")

        suggestions = [StyledString(comm)
                       for comm in COMMANDS_INFO.keys() if comm.startswith(token)]

        return SuggestionsIntent(suggestions,
                                 completion=True,
                                 space_after_completion=lambda s: not s.endswith("/"))


# ============ EXIT ================

class Exit(CommandInfo):

    @classmethod
    def name(cls):
        return "exit"

    @classmethod
    def short_description(cls):
        return "exit from the interactive shell"

    @classmethod
    def synopsis(cls):
        return """\
<b>exit</b>
<b>quit</b>
<b>q</b>"""

    @classmethod
    def long_description(cls):
        return f"""\
Exit from the interactive shell.

Open connections are automatically closed."""

# ============ TRACE ================

class Trace(CommandInfo):
    T0 = (["0"], "enable packet tracing")
    T1 = (["1"], "disable packet tracing")

    @classmethod
    def name(cls):
        return "trace"

    @classmethod
    def short_description(cls):
        return "enable/disable packet tracing"

    @classmethod
    def synopsis(cls):
        return """\
<b>trace</b>   [<u>0</u> | <u>1</u>]
<b>t</b>       [<u>0</u> | <u>1</u>]"""

    @classmethod
    def long_description(cls):
        return """\
Show (1) or hide (0) the packets sent and received to and from the server for any operation.

If no argument is given, toggle the packet tracing mode."""

    @classmethod
    def examples(cls):
        return """\
Usage example:

<b>/tmp</b> <b>t</b>
Tracing = 1 (enabled)
<b>/tmp</b> o temp
>> <broadcast>:12019
>>   DISCOVER (58140)

<< 192.168.1.105:57300
<<   DISCOVER
{
<i+2>"success": true,</i>
<i+2>"data": {</i>
<i+4>"name": "alice-arch",</i>
<i+4>"sharings": [</i>
<i+6>{</i>
<i+8>"name": "temp",</i>
<i+8>"ftype": "dir",</i>
<i+8>"read_only": false</i>
<i+6>}</i>
<i+4>],</i>
<i+4>"ssl": false,</i>
<i+4>"auth": false,</i>
<i+4>"ip": "192.168.1.105",</i>
<i+4>"port": 12020,</i>
<i+4>"discoverable": true,</i>
<i+4>"discover_port": 12019</i>
<i+2>}</i>
}

>> 192.168.1.105:12020 (stefano-arch)
>>   connect (password=None)

<< 192.168.1.105:12020 (stefano-arch)
<<   connect
{
<i+2>"success": true</i>
}

>> 192.168.1.105:12020 (stefano-arch)
>>   open ("temp")

<< 192.168.1.105:12020 (stefano-arch)
<<   open
{
<i+2>"success": true,</i>
<i+2>"data": "ebc40f8680d448dcad5c98291b720e37"</i>
}

<b>alice-arch.temp:/</b> - <b>/tmp></b>"""

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_string(justification=15 + 6))
             for info in [
                 CommandOptionInfo(None, params=Trace.T0[0], description=Trace.T0[1]),
                 CommandOptionInfo(None, params=Trace.T1[0], description=Trace.T1[1])
                ]
            ],
            completion=False,
            max_columns=1,
        )


# ============ VERBOSE ================


class Verbose(CommandInfo):
    V0 = (["0"], "disabled")
    V1 = (["1"], "error")
    V2 = (["2"], "warning")
    V3 = (["3"], "info")
    V4 = (["4"], "debug")
    V5 = (["5"], "internal libraries")

    @classmethod
    def name(cls):
        return "verbose"

    @classmethod
    def short_description(cls):
        return "change verbosity level"

    @classmethod
    def synopsis(cls):
        return """\
<b>verbose</b>   [<u>LEVEL/<u>]
<b>v</b>   [<u>LEVEL/<u>]"""

    @classmethod
    def long_description(cls):
        return """\
Change the verbosity level to <u>LEVEL</u> (default is <u>0</u>, which is disabled).

The messages are written to stdout.

The allowed value of <u>LEVEL</u> are:
<u>0</u>        disabled (default)
<u>1</u>        errors
<u>2</u>        warnings
<u>3</u>        info
<u>4</u>        debug
<u>5</u>        internal libraries

If no argument is given, increase the verbosity or resets \
it to <u>0</u> if it exceeds the maximum."""

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_string(justification=15 + 6))
             for info in [
                 CommandOptionInfo(None, params=Verbose.V0[0], description=Verbose.V0[1]),
                 CommandOptionInfo(None, params=Verbose.V1[0], description=Verbose.V1[1]),
                 CommandOptionInfo(None, params=Verbose.V2[0], description=Verbose.V2[1]),
                 CommandOptionInfo(None, params=Verbose.V3[0], description=Verbose.V3[1]),
                 CommandOptionInfo(None, params=Verbose.V4[0], description=Verbose.V4[1]),
                 CommandOptionInfo(None, params=Verbose.V5[0], description=Verbose.V5[1]),
                ]
            ],
            completion=False,
            max_columns=1,
        )


# ============ xPWD ================


class Pwd(CommandInfo):

    @classmethod
    def name(cls):
        return "pwd"

    @classmethod
    def short_description(cls):
        return "show the name of current local working directory"

    @classmethod
    def synopsis(cls):
        return "<b>pwd</b>"

    @classmethod
    def long_description(cls):
        return """\
Show the name of current local working directory.

The local working directory can be changed with the command <b>cd</b>."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rpwd</b>" for the remote analogous."""


class Rpwd(CommandInfo):

    @classmethod
    def name(cls):
        return "rpwd"

    @classmethod
    def short_description(cls):
        return "show the name of current remote working directory"

    @classmethod
    def synopsis(cls):
        return "<b>rpwd</b>"

    @classmethod
    def long_description(cls):
        return f"""\
Show the name of current remote working directory.

The remote working directory can be changed with the command <b>rcd</b>."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help pwd</b>" for the local analogous."""

# ============ xLS ================


class BaseLsCommandInfo(CommandInfo, ABC, Pargs):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.SORT_BY_SIZE, PRESENCE_PARAM),
            (self.REVERSE, PRESENCE_PARAM),
            (self.GROUP, PRESENCE_PARAM),
            (self.SHOW_ALL, PRESENCE_PARAM),
            (self.SHOW_DETAILS, PRESENCE_PARAM),
            (self.SHOW_SIZE, PRESENCE_PARAM),
        ]


    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.SORT_BY_SIZE, "sort by size"),
            CommandOptionInfo(cls.REVERSE, "reverse sort order"),
            CommandOptionInfo(cls.GROUP, "group by file type"),
            CommandOptionInfo(cls.SHOW_ALL, "show hidden files too"),
            CommandOptionInfo(cls.SHOW_SIZE, "show files size"),
            CommandOptionInfo(cls.SHOW_DETAILS, "show more details")
        ]

class Ls(BaseLsCommandInfo, ListLocalAllCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "ls"

    @classmethod
    def short_description(cls):
        return "list local directory content"

    @classmethod
    def synopsis(cls):
        return "<b>ls</b> [<u>OPTION</u>]... [<u>DIR</u>]"

    @classmethod
    def long_description(cls):
        return """\
List content of the local <u>DIR</u> or the current local directory if no <u>DIR</u> is specified."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rls</b>" for the remote analogous."""

class Rls(BaseLsCommandInfo, ListLocalAllCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rls"

    @classmethod
    def short_description(cls):
        return "list remote directory content"

    @classmethod
    def synopsis(cls):
        return """\
<b>rls</b> [<u>OPTION</u>]... [<u>DIR</u>]
<b>rls</b> [<u>OPTION</u>]... [<u>SHARING_LOCATION</u>] [<u>DIR</u>]"""

    @classmethod
    def long_description(cls):
        return f"""\
List content of the remote <u>DIR</u> or the current remote directory if no <u>DIR</u> is specified."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help ls</b>" for the local analogous."""

# ============ xL ================

# noinspection PyAbstractClass
class L(CommandInfo):
    @classmethod
    def custom(cls):
        return "alias for ls -la"


# noinspection PyAbstractClass
class Rl(CommandInfo):
    @classmethod
    def custom(cls):
        return "alias for rls -la"


# ============ xTREE ================

class BaseTreeCommandInfo(CommandInfo, ABC, Pargs):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    MAX_DEPTH = ["-d", "--depth"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.SORT_BY_SIZE, PRESENCE_PARAM),
            (self.REVERSE, PRESENCE_PARAM),
            (self.GROUP, PRESENCE_PARAM),
            (self.SHOW_ALL, PRESENCE_PARAM),
            (self.SHOW_DETAILS, PRESENCE_PARAM),
            (self.SHOW_SIZE, PRESENCE_PARAM),
            (self.MAX_DEPTH, INT_PARAM),
        ]

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.SORT_BY_SIZE, "sort by size"),
            CommandOptionInfo(cls.REVERSE, "reverse sort order"),
            CommandOptionInfo(cls.GROUP, "group by file type"),
            CommandOptionInfo(cls.SHOW_ALL, "show hidden files too"),
            CommandOptionInfo(cls.SHOW_SIZE, "show files size"),
            CommandOptionInfo(cls.SHOW_DETAILS, "show more details"),
            CommandOptionInfo(cls.MAX_DEPTH, "maximum display depth of tree", params=["depth"])
        ]


class Tree(BaseTreeCommandInfo, ListLocalAllCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "tree"

    @classmethod
    def short_description(cls):
        return "list local directory contents in a tree-like format"

    @classmethod
    def synopsis(cls):
        return "<b>tree</b> [<u>OPTION</u>]... [<u>DIR</u>]"

    @classmethod
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the local <u>DIR</u> or the current \
local directory if no <u>DIR</u> is specified."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rtree</b>" for the remote analogous."""


class Rtree(BaseTreeCommandInfo, ListLocalAllCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "<b>rtree</b>"

    @classmethod
    def short_description(cls):
        return "list remote directory contents in a tree-like format"

    @classmethod
    def synopsis(cls):
        return "<b>tree</b> [<u>OPTION</u>]... [<u>DIR</u>]"

    @classmethod
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the remote <u>DIR</u> or the current \
remote directory if no <u>DIR</u> is specified"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help tree</b>" for the local analogous."""

# ============ xCD ================


class Cd(ListLocalDirsCommandInfo):

    @classmethod
    def name(cls):
        return "cd"

    @classmethod
    def short_description(cls):
        return "change local working directory"

    @classmethod
    def synopsis(cls):
        return "<b>cd</b> [<u>DIR</u>]"

    @classmethod
    def long_description(cls):
        return """\
Change the current local working directory to <u>DIR</u> or to the user's home \
directory if <u>DIR</u> is not specified."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rcd</b>" for the remote analogous."""


class Rcd(CommandInfo):

    @classmethod
    def name(cls):
        return "rcd"

    @classmethod
    def short_description(cls):
        return "change remote working directory"

    @classmethod
    def synopsis(cls):
        return """\
<b>rcd</b> [<u>DIR</u>]"""

    @classmethod
    def long_description(cls):
        return f"""\
Change the current remote working directory to <u>DIR</u> or to the root of \
the current sharing if no <u>DIR</u> is specified."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rcd</b> <u>dir</u>
<b>bob-debian.music:/dir</b> - <b>/tmp></b> <b>rcd</b> <u>subdir</u>
<b>bob-debian.music:/dir/subdir</b> - <b>/tmp></b>"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help cd</b>" for the local analogous."""


# ============ xMKDIR ================


class Mkdir(CommandInfo):

    @classmethod
    def name(cls):
        return "mkdir"

    @classmethod
    def short_description(cls):
        return "create a local directory"

    @classmethod
    def synopsis(cls):
        return "<b>mkdir</b> <u>DIR</u>"

    @classmethod
    def long_description(cls):
        return """\
Create the local directory <u>DIR</u>.

Parent directories of <u>DIR</u> are automatically created when needed.

If <u>DIR</u> already exists, it does nothing."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rmkdir</b>" for the remote analogous."""


class Rmkdir(FastSharingConnectionCommandInfo):

    @classmethod
    def name(cls):
        return "rmkdir"

    @classmethod
    def short_description(cls):
        return "create a remote directory"

    @classmethod
    def synopsis(cls):
        return """\
<b>rmkdir</b> <u>DIR</u>
<b>rmkdir</b> [<u>SHARING_LOCATION</u>] <u>DIR</u>"""

    @classmethod
    def long_description(cls):
        return f"""\
Create the remote directory <u>DIR</u>.

Parent directories of <u>DIR</u> are automatically created when needed.

If <u>DIR</u> already exists, it does nothing."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rmkdir</b> <u>newdir</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rcd newdir
<b>bob-debian.music:/newdir</b> - <b>/tmp></b>"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help mkdir</b>" for the local analogous."""


# ============ xCP ================


class Cp(CommandInfo):

    @classmethod
    def name(cls):
        return "cp"

    @classmethod
    def short_description(cls):
        return "copy files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
<b>cp</b> <u>SOURCE</u> <u>DEST</u>
<b>cp</b> <u>SOURCE</u>... <u>DIR</u>"""

    @classmethod
    def long_description(cls):
        return """\
Copy local <u>SOURCE</u> file or directory to <u>DEST</u>, \
or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>cp</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
  <a>
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>
  </a>
If used with at least arguments as "<b>cp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be copied into it."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rcp</b>" for the remote analogous."""


class Rcp(FastSharingConnectionCommandInfo):

    @classmethod
    def name(cls):
        return "rcp"

    @classmethod
    def short_description(cls):
        return "copy files and directories remotely"

    @classmethod
    def synopsis(cls):
        return """\
<b>rcp</b> <u>SOURCE</u> <u>DEST</u>
<b>rcp</b> <u>SOURCE</u>... <u>DIR</u>
<b>rcp</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u> <u>DEST</u>
<b>rcp</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u>... <u>DIR</u>"""

    @classmethod
    def long_description(cls):
        return """\
Copy remote <u>SOURCE</u> file or directory to <u>DEST</u>, \
or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rcp</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
  <a>
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>
  </a>
If used with at least arguments as "<b>rcp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be copied into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f1
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rcp</b> <u>f1</u> <u>f2</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f1      f2

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree
|-- dir
|-- f1
+-- f2
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rcp</b> <u>f1</u> <u>f2</u> <u>dir</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree dir
|-- dir
|   |-- f1
|   +-- f2
|-- f1
+-- f2"""


    @classmethod
    def see_also(cls):
        return """Type "<b>help cp</b>" for the local analogous."""



# ============ xMV ================


class Mv(CommandInfo):

    @classmethod
    def name(cls):
        return "mv"

    @classmethod
    def short_description(cls):
        return "move files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
<b>mv</b> <u>SOURCE</u> <u>DEST</u>
<b>mv</b> <u>SOURCE</u>... <u>DIR</u>"""

    @classmethod
    def long_description(cls):
        return """\
Move local <u>SOURCE</u> file or directory to <u>DEST</u>, \
or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>mv</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
  <a>
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>
  </a>
If used with at least arguments as "<b>mv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be moved into it."""


    @classmethod
    def see_also(cls):
        return """Type "<b>help rmv</b>" for the remote analogous."""



class Rmv(FastSharingConnectionCommandInfo):

    @classmethod
    def name(cls):
        return "rmv"

    @classmethod
    def short_description(cls):
        return "move files and directories remotely"

    @classmethod
    def synopsis(cls):
        return """\
<b>rmv</b> <u>SOURCE</u> <u>DEST</u>
<b>rmv</b> <u>SOURCE</u>... <u>DIR</u>
<b>rmv</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u> <u>DEST</u>
<b>rmv</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u>... <u>DIR</u>"""

    @classmethod
    def long_description(cls):
        return """\
Move remote <u>SOURCE</u> file or directory to <u>DEST</u>, \
or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rmv</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
  <a>
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>
  </a>
If used with at least arguments as "<b>rmv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be moved into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f1
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rmv</b> <u>f1</u> <u>f2</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f2

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree
|-- dir
|-- f1
+-- f2
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rmv</b> <u>f1</u> <u>f2</u> <u>dir</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree dir
+-- dir
    |-- f1
    +-- f2"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help mv</b>" for the local analogous."""


# ============ xRM ================


class Rm(CommandInfo):

    @classmethod
    def name(cls):
        return "rm"

    @classmethod
    def short_description(cls):
        return "remove files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
<b>rm</b> [FILE]..."""

    @classmethod
    def long_description(cls):
        return """\
Remove local <u>FILE</u>s.

If a <u>FILE</u> is a directory, it will be removed recursively.

If a <u>FILE</u> does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf."""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rrm</b>" for the remote analogous."""



class Rrm(FastSharingConnectionCommandInfo):

    @classmethod
    def name(cls):
        return "rrm"

    @classmethod
    def short_description(cls):
        return "remove files and directories remotely"

    @classmethod
    def synopsis(cls):
        return """\
<b>rrm</b> [FILE]...
<b>rrm</b> [<u>SHARING_LOCATION</u>] [FILE]..."""

    @classmethod
    def long_description(cls):
        return """\
Remove remote <u>FILE</u>s.

If a <u>FILE</u> is a directory, it will be removed recursively.

If a <u>FILE</u> does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f1      f2
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rrm</b> <u>f2</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> <rls
f1

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree
|-- dir
|   |-- f1
|   +-- f2
+-- f1
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rrm</b> <u>dir</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> rtree
+-- f1"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rm</b>" for the local analogous."""


# ============ xEXEC ================


class Exec(CommandInfo):

    @classmethod
    def name(cls):
        return "exec"

    @classmethod
    def short_description(cls):
        return "execute an arbitrary command locally"

    @classmethod
    def synopsis(cls):
        return """\
<b>exec</b> <u>COMMAND</u>
<b>:</b> <u>COMMAND</u>
<b>:</b><u>COMMAND</u>"""

    @classmethod
    def long_description(cls):
        return """\
Executes an arbitrary <u>COMMAND</u> locally.

The <u>COMMAND</u> is executed via the shell and therefore allows all the \
shell features (e.g. variables, glob expansions, redirection).

This might be useful for execute commands without exiting the easyshare's shell.

The command can be run either with "<b>exec</b> <u>COMMAND</u>",  \
"<b>:</b> <u>COMMAND</u>" or "<b>:</b><u>COMMAND</u>"."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> ls
f1      f2
<b>/tmp></b> <b>exec</b> <u>touch f3</u>
f1      f2      f3
<b>/tmp></b> <b>:</b> <u>echo "hello" > f3</u>
<b>/tmp></b> <b>:</b><u>cat f3</u>
hello"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help rexec</b>" for the remote analogous."""


class Rexec(FastServerConnectionCommandInfo):

    @classmethod
    def name(cls):
        return "rexec"

    @classmethod
    def short_description(cls):
        return "execute an arbitrary command remotely"

    @classmethod
    def synopsis(cls):
        return """\
<b>rexec</b> <u>COMMAND</u>
<b>::</b> <u>COMMAND</u>
<b>::</b><u>COMMAND</u>

<b>rexec</b> [<u>SERVER_LOCATION</u>] <u>COMMAND</u>
<b>::</b> [<u>SERVER_LOCATION</u>] <u>COMMAND</u>
<b>::</b>[<u>SERVER_LOCATION</u>] <u>COMMAND</u>"""

    @classmethod
    def long_description(cls):
        return """\
THE SERVER REJECTS THIS COMMAND BY DEFAULT, UNLESS IT HAS BEEN MANUALLY \
ENABLED WITH THE SETTING "<u>rexec=true</u>"

Executes an arbitrary <u>COMMAND</u> remotely.

The <u>COMMAND</u> is executed via the shell and therefore allows all the \
shell features (e.g. variables, glob expansions, redirection).

This might be useful for execute commands remotely, giving the client \
a kind of easy and plug-and-play shell.

The command can be run either with "<b>rexec</b> <u>COMMAND</u>",  \
"<b>::</b> <u>COMMAND</u>" or "<b>::</b><u>COMMAND</u>"."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> rls
f1      f2
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>rexec</b> <u>touch f3</u>
f1      f2      f3
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>::</b> <u>echo "hello" > f3</u>
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>::</b><u>cat f3</u>
hello"""

    @classmethod
    def see_also(cls):
        return """Type "<b>help exec</b>" for the local analogous."""


# ============ SCAN ================


class Scan(CommandInfo, NoPargs):
    SHOW_SHARINGS_DETAILS = ["-l"]
    SHOW_ALL_DETAILS = ["-L"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.SHOW_SHARINGS_DETAILS, PRESENCE_PARAM),
            (self.SHOW_ALL_DETAILS, PRESENCE_PARAM),
        ]

    @classmethod
    def name(cls):
        return "scan"

    @classmethod
    def short_description(cls):
        return "scan the network for easyshare servers"

    @classmethod
    def synopsis(cls):
        return """\
<b>scan</b> [<u>OPTION</u>]...
<b>s</b> [<u>OPTION</u>]..."""

    @classmethod
    def long_description(cls):
        return """\
Scan the network for easyshare server and reports the details \
of the sharings found.

The discover is performed in broadcast in the network.

The port on which the discover is performed is the one specified to \
<b>es</b> via <b>-d</b> <u>port</u>, or the default one if not specified.

The scan time is two seconds unless it has been specified to <b>es</b> via <b>-w</b> <u>seconds</u>.

Only details about the sharings are shown, unless <b>-L</b> is given."""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.SHOW_SHARINGS_DETAILS, "show more details of sharings"),
            CommandOptionInfo(cls.SHOW_ALL_DETAILS, "show more details of both servers and sharings"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> <b>scan</b>
<b>alice-arch (192.168.1.105:12020)</b>
  DIRECTORIES
  - shared
  - tmp
<b>bob-debian (192.168.1.185:12020)</b>
  DIRECTORIES
  - music
  FILES
  - README.txt"""


# ============ CONNECT ================


class Connect(CommandInfo):

    @classmethod
    def name(cls):
        return "connect"

    @classmethod
    def short_description(cls):
        return "connect to a remote server"

    @classmethod
    def synopsis(cls):
        return """\
<b>connect</b> <u>SERVER_LOCATION</u>"""

    @classmethod
    def long_description(cls):
        return """\
Connect to a remote server whose location is specified by <u>SERVER_LOCATION</u>.

<u>SERVER_LOCATION</u> has the following syntax:
<i+4><<u>server_name</u>> or <<u>address</u>>[:<<u>port</u>>]</i>

See the section <b>EXAMPLES</b> for more examples about <u>SERVER_LOCATION</u>.
   <a>
The following rules are applied for establish a connection:
1. If <u>SERVER_LOCATION</u> is a valid <<u>server_name</u>> (e.g. alice-arch), \
a discover is performed for figure out which port the server is bound to.
2. If <u>SERVER_LOCATION</u> has the form <<u>address</u>> (e.g. 192.168.1.105), \
the connection will be tried to be established directly to the server at the the default port. \
If the attempt fails, a discover is performed for figure out which port \
the server is really bound to and another attempt is done.
3. If <u>SERVER_LOCATION</u> has the form <<u>address</u>>:<<u>port</u>> \
(e.g, 182.168.1.106:22020), the connection will be established directly.
   </a>
The discover, if involved (1. and 2.), is performed on the port specified to <b>es</b>\
with <b>-d</b> <u>port</u> for the time specified with <b>-w</b> <u>seconds</u> \
(default is two seconds).

Note that <b>connect</b> is not necessary if you want to directly open a sharing, \
you can use <b>open</b> which automatically will establish the connection with \
the server as <b>connect</b> would do.

There might be cases in which use <b>connect</b> is still required, for example \
for execute server commands (i.e. info, ping, list, rexec) which are not related \
to any sharings (you can use those commands if connected to a sharing, by the way).

When possible, using "<b>connect</b> <<u>server_name</u>>" (1.) is more immediate \
and human friendly compared to specify the address and eventually the port of \
the server (2. and 3.).

There are cases in which specify the address and the port of the server (3.) is \
necessary, for example when the discover can't be performed because the server \
is not on the same network of the client (e.g. behind a NAT).

If already connected to a server, a successful <b>connect</b> execution to another server \
automatically closes the current connection.

Remember that <b>connect</b> establish the connection with the server, but do \
not place you inside any server's sharing. Use <b>open</b> for that."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1. Connection by server name (discover)
<b>/tmp></b> <b>connect</b> <u>alice-arch</u>
<b>alice-arch</b> - <b>/tmp></b> list
DIRECTORIES
- shared
- tmp

2. Connection by address (direct attempt, discover if fails)
<b>/tmp></b> <b>connect</b> <u>192.168.1.105</u>
<b>alice-arch</b> - <b>/tmp></b>

3. Connection by address and port (direct)
<b>/tmp></b> <b>connect</b> <u>89.1.2.84:22020</u>
<b>eve-kali</b> - <b>/tmp></b>"""

    @classmethod
    def see_also(cls):
        return "<b>disconnect></b>, <b>open</b>"


# ============ DISCONNECT ================


class Disconnect(CommandInfo):

    @classmethod
    def name(cls):
        return "disconnect"

    @classmethod
    def short_description(cls):
        return "disconnect from a remote server"

    @classmethod
    def synopsis(cls):
        return """\
<b>disconnect</b>"""

    @classmethod
    def long_description(cls):
        return """\
Disconnect from the remote server to which the connection is established.

While this command is the counterpart of <b>connect</b>, it can be used to \
close connections opened in other ways (i.e. with <b>open</b>).

This differs from <b>close</b> which closes only the currently opened sharing \
without closing the connection."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> <b>disconnect</b>
<b>/tmp></b> connect"""

    @classmethod
    def see_also(cls):
        return "<b>connect</b>, <b>close</b>"


# ============ OPEN ================


class Open(CommandInfo):

    @classmethod
    def name(cls):
        return "open"

    @classmethod
    def short_description(cls):
        return "open a remote sharing (eventually discovering it)"

    @classmethod
    def synopsis(cls):
        return """\
<b>open</b> <u>SHARING_LOCATION</u>"""

    @classmethod
    def long_description(cls):
        return """\
Open a sharing whose location is specified by <u>SHARING_LOCATION</u>

<u>SHARING_LOCATION</u> has the following syntax:
<i+4><<u>sharing_name</u>>[@<<u>server_name</u>>|<<u>address</u>>[:<<u>port</u>>]]</i>

See the section <b>EXAMPLES</b> for more examples about <u>SHARING_LOCATION</u>.

The following rules are applied for establish a connection:
   <a>
1. If <u>SHARING_LOCATION</u> is a valid <<u>sharing_name</u>> (e.g. shared), \
a discover is performed for figure out to which server the sharing belongs to.
2. If <u>SHARING_LOCATION</u> has the form <<u>sharing_name</u>>@<<u>server_name</u>>[:port] \
(e.g. shared@alice-arch) a discover is performed as well as in case 1. and the \
<<u>server_name</u>> and the <<u>port</u>> act only as a filter \
(i.e. the connection won't be established if they don't match).
3. If <u>SHARING_LOCATION</u> has the form <<u>sharing_name</u>>@<<u>address</u>> \
(e.g. shared@192.168.1.105) the connection will be tried to be established \
directly to the server at the default port. If the attempt fails, a discover \
is performed for figure out which port the server is really bound to and \
another attempt is done.
4. If <u>SHARING_LOCATION</u> has the form <<u>sharing_name</u>>@<<u>address</u>>:<<u>port</u>> \
(e.g. shared@192.168.1.105:12020) the connection will be established directly.
   </a>
The discover, if involved (1., 2. and 3.), is performed on the port specified to <b>es</b> \
with <b>-d</b> <u>port</u> for the time specified with <b>-w</b> <u>seconds</u> \
(default is two seconds).

Note that <b>connect</b> is not necessary if you want to directly open a sharing, \
you can use <b>open</b> which automatically will establish the connection with \
the server as <b>connect</b> would do.

When possible, using the server name (1., 2. and 3.) is more immediate \
and human friendly compared to specify the address and eventually the port of \
the server (4.).

There are cases in which specify the address and the port of the server (4.) is \
necessary, for example when the discover can't be performed because the server \
is not on the same network of the client (e.g. behind a NAT).

If the sharing described by <u>SHARING_LOCATION</u> is found within the sharings \
of the server to which the connection is already established, it will be obviously \
opened without perform any kind of discover or new connection.

If already connected to a server and/or a sharing, a successful <b>open</b> \
execution to another server automatically closes the current connection.

If, for some reason, there is more than a sharing with the same name on the same \
network, <b>open</b> will try to connect to the one that is discovered first \
(in general it's unpredictable which will be).

If you need a deterministic (and more safe) approach, consider using <b>scan</b> \
for discover the server manually (eventually followed by a consecutive <b>info</b> call \
for fetch more accurate details such as SSL certificate) then invoke <b>open</b> \
specifying the server details too (i.e. server name or address and port).

In general, <b>open</b> doesn't require you to use <b>connect</b> before; the \
connection will be created for you automatically."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1. Connection by sharing name (while connected)
<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> <b>open</b> <u>temp</u>
<b>alice-arch.temp:/</b> - <b>/tmp></b> rls
f1      f2

1. Connection by sharing name (discover)
<b>/tmp></b> <b>open<b> temp
<b>alice-arch.temp:/</b> - <b>/tmp></b> rls
f1      f2

2. Connection by sharing name with server name filter (discover)
<b>/tmp></b> <b>open</b> <u>temp@alice-arch</u>
<b>alice-arch.temp:/</b> - <b>/tmp></b>

3. Connection by sharing name with address (attempt direct, discover if fails)
<b>/tmp></b> <b>open</b> <u>temp@alice-arch</u>
<b>alice-arch.temp:/</b> - <b>/tmp></b>

4. Connection by sharing name with address and port (direct)
<b>/tmp></b> <b>open</b> <u>temp@192.168.1.105:12020</u>
<b>alice-arch.temp:/</b> - <b>/tmp></b>"""

    @classmethod
    def see_also(cls):
        return "<b>close></b>, <b>connect</b>"


# ============ CLOSE ================


class Close(CommandInfo):

    @classmethod
    def name(cls):
        return "close"

    @classmethod
    def short_description(cls):
        return "close the remote sharing"

    @classmethod
    def synopsis(cls):
        return """\
<b>close</b>"""

    @classmethod
    def long_description(cls):
        return """\
Close the currently opened sharing.

If the sharing connection has been created directly with <b>open</b> instead of \
<b>connect</b> and then <b>open</b>, than the server connection is closed too (for symmetry)."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1. Close sharing connection only
<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> open shared
<b>alice-arch.shared:/</b> - <b>/tmp></b> <b>close</b>
<b>alice-arch</b> - <b>/tmp></b> <b>close</b>

2. Close both sharing and server connection
<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>close</b>
<b>/tmp></b>"""

    @classmethod
    def see_also(cls):
        return "<b>open</b>, <b>disconnect</b>"


# ============ LIST ================


class ListSharings(FastServerConnectionCommandInfo, NoPargs):
    SHOW_DETAILS = ["-l"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.SHOW_DETAILS, PRESENCE_PARAM),
        ]

    @classmethod
    def name(cls):
        return "list"

    @classmethod
    def short_description(cls):
        return "list the sharings of the remote server"

    @classmethod
    def synopsis(cls):
        return """\
<b>list</b> [<u>OPTION</u>]...
<b>list</b> [<u>SERVER_LOCATION</u>] [<u>OPTION</u>]..."""

    @classmethod
    def long_description(cls):
        return """\
List the sharings of the remote server to which the connection is established."""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.SHOW_DETAILS, "show more details of sharings"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> <b>list</b>
DIRECTORIES
- shared
- tmp

<b>/tmp></b> open music
<b>bob-debian.music:/</b> - <b>/tmp></b> <b>list</b>
DIRECTORIES
- music
FILES
- README.txt"""



# ============ INFO ================


class Info(FastServerConnectionCommandInfo, NoPargs):
    SHOW_SHARINGS_DETAILS = ["-l"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.SHOW_SHARINGS_DETAILS, PRESENCE_PARAM),
        ]

    @classmethod
    def name(cls):
        return "info"

    @classmethod
    def short_description(cls):
        return "show information about the remote server"

    @classmethod
    def synopsis(cls):
        return """\
<b>info</b> [<u>OPTION</u>]...
<b>info</b> [<u>SERVER_LOCATION</u>] [<u>OPTION</u>]..."""

    @classmethod
    def long_description(cls):
        return """\
Show information of the remote server to which the connection is established.

The reported information are: 
- Server name
- Server ip
- Server port
- Server discover port
- Authentication enabled/disabled
- SSL enabled/disabled 
- SSL certificate info (if enabled)
- Sharings"""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.SHOW_SHARINGS_DETAILS, "show more details of sharings"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> <b>info</b>
================================

SERVER INFO

Name:           alice-arch
IP:             192.168.1.105
Port:           12020
Discoverable:   True
Discover Port:  12019
Auth:           False
SSL:            True

================================

SSL CERTIFICATE

Common name:        192.168.1.105
Organization:       Acme Corporation
Organization Unit:  Acme Corporation
Email:              acme@gmail.com
Locality:           Los Angeles
State:              Los Angeles
Country:            US

Valid From:         Apr 24 21:29:46 2020 GMT
Valid To:           Apr 24 21:29:46 2021 GMT

Issuer:             192.168.1.105, Acme Corporation
Signing:            self signed

================================

SHARINGS

  DIRECTORIES
  - tmp

================================"""


# ============ PING ================


class Ping(FastServerConnectionCommandInfo, NoPargs):
    COUNT = ["-c", "--count"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.COUNT, PRESENCE_PARAM),
        ]

    @classmethod
    def name(cls):
        return "ping"

    @classmethod
    def short_description(cls):
        return "test the connection with the remote server"

    @classmethod
    def synopsis(cls):
        return """\
<b>ping</b> [<u>OPTION</u>]...
<b>ping</b> [<u>SERVER_LOCATION</u>] [<u>OPTION</u>]..."""

    @classmethod
    def long_description(cls):
        return """\
Test the connectivity with the server by sending an application-level message."""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.COUNT, "stop after <u>count</u> messages", ["count"]),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> connect alice-arch
<b>alice-arch</b> - <b>/tmp></b> <b>ping</b>
[1] PONG from alice-arch (192.168.1.105:12020)  |  time=5.1ms
[2] PONG from alice-arch (192.168.1.105:12020)  |  time=0.9ms
...

<b>/tmp></b> <b>ping</b> <u>bob-debian</u> <b>-c</b> <u>1</u>
[1] PONG from bob-debian (192.168.1.185:12020)  |  time=9.3ms

<b>/tmp></b> <b>ping</b> <u>192.168.1.185</u> <b>-c</b> <u>1</u>
[1] PONG from bob-debian (192.168.1.185:12020)  |  time=10.3ms"""

# class LsEnhancedCommandInfo(ListLocalAllCommandInfo):
#     pass
#
#
# class RlsCommandInfo(BaseLsCommandInfo, ListRemoteAllCommandInfo):
#     pass
#
#
# class BaseTreeCommandInfo(CommandWithArgsInfo):
#     SORT_BY_SIZE = CommandArgInfo(["-s", "--sort-size"], "Sort by size")
#     REVERSE = CommandArgInfo(["-r", "--reverse"], "Reverse sort order")
#     GROUP = CommandArgInfo(["-g", "--group"], "Group by file type")
#     MAX_DEPTH = CommandArgInfo(["-d", "--depth"], "Maximum depth")
#     SIZE = CommandArgInfo(["-S"], "Show file size")
#     DETAILS = CommandArgInfo(["-l"], "Show all the details")
#
#
# class TreeCommandInfo(BaseTreeCommandInfo, ListLocalAllCommandInfo):
#     pass
#
#
# class RtreeCommandInfo(BaseTreeCommandInfo, ListRemoteAllCommandInfo):
#     pass
#
#
# class GetCommandInfo(ListRemoteAllCommandInfo):
#     YES_TO_ALL = CommandArgInfo(["-Y", "--yes"], "Always overwrite existing files")
#     NO_TO_ALL = CommandArgInfo(["-N", "--no"], "Never overwrite existing files")
#
#
# class PutCommandInfo(ListLocalAllCommandInfo):
#     YES_TO_ALL = CommandArgInfo(["-Y", "--yes"], "Always overwrite existing files")
#     NO_TO_ALL = CommandArgInfo(["-N", "--no"], "Never overwrite existing files")
#
#
# class ScanCommandInfo(CommandWithArgsInfo):
#     DETAILS = CommandArgInfo(["-l"], "Show all the details")
#


COMMANDS_INFO: Dict[str, Type[CommandInfo]] = {
    Commands.HELP: Help,
    Commands.HELP_SHORT: Help,
    Commands.EXIT: Exit,
    Commands.QUIT: Exit,
    Commands.QUIT_SHORT: Exit,

    Commands.TRACE: Trace,
    Commands.TRACE_SHORT: Trace,

    Commands.VERBOSE: Verbose,
    Commands.VERBOSE_SHORT: Verbose,

    Commands.LOCAL_CURRENT_DIRECTORY: Pwd,
    Commands.LOCAL_LIST_DIRECTORY: Ls,
    Commands.LOCAL_LIST_DIRECTORY_ENHANCED: L,
    Commands.LOCAL_TREE_DIRECTORY: Tree,
    Commands.LOCAL_CHANGE_DIRECTORY: Cd,
    Commands.LOCAL_CREATE_DIRECTORY: Mkdir,
    Commands.LOCAL_COPY: Cp,
    Commands.LOCAL_MOVE: Mv,
    Commands.LOCAL_REMOVE: Rm,
    Commands.LOCAL_EXEC: Exec,
    Commands.LOCAL_EXEC_SHORT: Exec,

    Commands.REMOTE_CURRENT_DIRECTORY: Rpwd,
    Commands.REMOTE_LIST_DIRECTORY: Rls,
    Commands.REMOTE_LIST_DIRECTORY_ENHANCED: Rl,
    Commands.REMOTE_TREE_DIRECTORY: Rtree,
    Commands.REMOTE_CHANGE_DIRECTORY: Rcd,
    Commands.REMOTE_CREATE_DIRECTORY: Rmkdir,
    Commands.REMOTE_COPY: Rcp,
    Commands.REMOTE_MOVE: Rmv,
    Commands.REMOTE_REMOVE: Rrm,
    Commands.REMOTE_EXEC: Rexec,
    Commands.REMOTE_EXEC_SHORT: Rexec,

    Commands.SCAN: Scan,
    Commands.SCAN_SHORT: Scan,

    Commands.CONNECT: Connect,
    Commands.DISCONNECT: Disconnect,

    Commands.OPEN: Open,
    Commands.OPEN_SHORT: Open,
    Commands.CLOSE: Close,
    Commands.CLOSE_SHORT: Close,

    # GET = "get"
    # GET_SHORT = "g"
    # PUT = "put"
    # PUT_SHORT = "p"
    #

    Commands.LIST: ListSharings,
    Commands.INFO: Info,
    Commands.INFO_SHORT: Info,
    Commands.PING: Ping,
}

