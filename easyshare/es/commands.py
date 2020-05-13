import os
from abc import abstractmethod, ABC
from typing import List, Callable, Union, Optional, Dict, Type

from easyshare.args import KwArg, PositionalArgs, PRESENCE_PARAM, INT_PARAM
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
    LIST = "list"

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

SHARING_LOCATION_IF_NOT_CONNECTED_DESC = """\
SHARING_LOCATION must be specified if and only if not already \
connected to a remote sharing. In that case the connection will be \
established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format."""


class RemoteSharingCommandInfo(CommandInfo, ABC):
    @classmethod
    def synopsis_extra(cls):
        return SHARING_LOCATION_IF_NOT_CONNECTED_DESC

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

If no argument is given, toggle the packet tracing mode.
"""

    @classmethod
    def examples(cls):
        return """\
Here are some examples of data shown with the packet tracing on.

{
    TODO: example
}"""

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
<b>verbose</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]
<b>v</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]"""

    @classmethod
    def long_description(cls):
        pass

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


class Rpwd(RemoteSharingCommandInfo):

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


# ============ xLS ================


class BaseLsCommandInfo(CommandInfo, ABC, PositionalArgs):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

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

    def kwargs_specs(self) -> Optional[List[KwArg]]:
        return [
            (self.SORT_BY_SIZE, PRESENCE_PARAM),
            (self.REVERSE, PRESENCE_PARAM),
            (self.GROUP, PRESENCE_PARAM),
            (self.SHOW_ALL, PRESENCE_PARAM),
            (self.SHOW_DETAILS, PRESENCE_PARAM),
            (self.SHOW_SIZE, PRESENCE_PARAM),
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

class Rls(BaseLsCommandInfo, ListLocalAllCommandInfo, RemoteSharingCommandInfo):
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

class BaseTreeCommandInfo(CommandInfo, ABC, PositionalArgs):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    MAX_DEPTH = ["-d", "--depth"]

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

    def kwargs_specs(self) -> Optional[List[KwArg]]:
        return [
            (self.SORT_BY_SIZE, PRESENCE_PARAM),
            (self.REVERSE, PRESENCE_PARAM),
            (self.GROUP, PRESENCE_PARAM),
            (self.SHOW_ALL, PRESENCE_PARAM),
            (self.SHOW_DETAILS, PRESENCE_PARAM),
            (self.SHOW_SIZE, PRESENCE_PARAM),
            (self.MAX_DEPTH, INT_PARAM),
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

class Rtree(BaseTreeCommandInfo, ListLocalAllCommandInfo, RemoteSharingCommandInfo):
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



# ============ xCD ================


class Cd(CommandInfo):

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

class Rcd(RemoteSharingCommandInfo):

    @classmethod
    def name(cls):
        return "rcd"

    @classmethod
    def short_description(cls):
        return "change remote working directory"

    @classmethod
    def synopsis(cls):
        return """\
<b>rcd</b> [<u>DIR</u>]
<b>rcd</b> [<u>SHARING_LOCATION</u>] [<u>DIR</u>]"""

    @classmethod
    def long_description(cls):
        return f"""\
Change the current remote working directory to <u>DIR</u> or to the root of \
the current sharing if no <u>DIR</u> is specified."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> <b>rcd</b> dir
<b>/tmp - remote.shared:/dir></b> <b>rcd</b> subdir
<b>/tmp - remote.shared:/dir/subdir></b> <b>rcd</b>
<b>/tmp - remote.shared:/></b>"""


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

class Rmkdir(RemoteSharingCommandInfo):

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

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> <b>rmkdir</b> newdir
<b>/tmp - remote.shared:/></b> rcd newdir
<b>/tmp - remote.shared:/newdir></b>"""



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
Copy <u>SOURCE</u> file or directory to <u>DEST</u>, \
or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>cp</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>cp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be copied into it."""

class Rcp(RemoteSharingCommandInfo):

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
Copy <u>SOURCE</u> file or directory to <u>DEST</u>, \
or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rcp</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>rcp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be copied into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rls
f1
<b>/tmp - remote.shared:/></b> <b>rcp</b> f1 f2
<b>/tmp - remote.shared:/></b> rls
f1      f2

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> tree
├── dir
├── f1
└── f2
<b>/tmp - remote.shared:/></b> <b>rcp</b> f1 f2 dir
<b>/tmp - remote.shared:/></b> rtree dir
├── dir
│   ├── f1
│   └── f2
├── f1
└── f2"""

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
Move <u>SOURCE</u> file or directory to <u>DEST</u>, \
or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>mv</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>mv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be moved into it."""

class Rmv(RemoteSharingCommandInfo):

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
Move <u>SOURCE</u> file or directory to <u>DEST</u>, \
or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rmv</b> <u>SOURCE</u> <u>DEST</u>" the following \
rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>rmv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must \
be an existing directory and <u>SOURCE</u>s will be moved into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rls
f1
<b>/tmp - remote.shared:/></b> <b>rmv</b> f1 f2
<b>/tmp - remote.shared:/></b> rls
f2

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rtree
├── dir
├── f1
└── f2
<b>/tmp - remote.shared:/></b> <b>rmv</b> f1 f2 dir
<b>/tmp - remote.shared:/></b> rtree dir
└── dir
    ├── f1
    └── f2"""

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
    # LOCAL_REMOVE = "rm"
    # LOCAL_EXEC = "exec"
    # LOCAL_EXEC_SHORT = SPECIAL_COMMAND_MARK
    #
    Commands.REMOTE_CURRENT_DIRECTORY: Rpwd,
    Commands.REMOTE_LIST_DIRECTORY: Rls,
    Commands.REMOTE_LIST_DIRECTORY_ENHANCED: Rl,
    Commands.REMOTE_TREE_DIRECTORY: Rtree,
    Commands.REMOTE_CHANGE_DIRECTORY: Rcd,
    Commands.REMOTE_CREATE_DIRECTORY: Rmkdir,
    Commands.REMOTE_COPY: Rcp,
    Commands.REMOTE_MOVE: Rmv,
    # REMOTE_REMOVE = "rrm"
    # REMOTE_EXEC = "rexec"
    # REMOTE_EXEC_SHORT = SPECIAL_COMMAND_MARK * 2
    #
    # SCAN = "scan"
    # SCAN_SHORT = "s"
    # LIST = "list"
    #
    # CONNECT = "connect"
    # DISCONNECT = "disconnect"
    #
    # OPEN = "open"
    # OPEN_SHORT = "o"
    # CLOSE = "close"
    # CLOSE_SHORT = "c"
    #
    # GET = "get"
    # GET_SHORT = "g"
    # PUT = "put"
    # PUT_SHORT = "p"
    #
    # INFO = "info"
    # INFO_SHORT = "i"
    # PING = "ping"
}

