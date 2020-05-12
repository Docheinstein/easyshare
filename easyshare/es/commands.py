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
    def __init__(self, aliases: Optional[List[str]], description: str, param: str = None):
        self.aliases = aliases
        self.description = description
        self.param = param

    def aliases_string(self) -> str:
        if not self.aliases:
            return ''
        return ', '.join(self.aliases)

    def to_string(self, justification: int = 0):
        return CommandOptionInfo._to_string(
            self.aliases_string() or "",
            self.param or "",
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
    def long_description(cls):
        pass

    @classmethod
    @abstractmethod
    def synopsis(cls):
        pass

    @classmethod
    def synopsis_extra(cls):
        return None

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

        longest_option_w_param = 0

        for opt in options:
            longest_option_w_param = max(
                longest_option_w_param,
                len(opt.aliases_string()) + len(" ") + len(opt.param)
            )

        log.d("Longest longest_option_w_param string length: %d", longest_option_w_param)

        suggestions = []
        i = 0

        # TODO param

        for opt in options:
            suggestions.append(StyledString(
                opt.to_string(justification=longest_option_w_param + 6)
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
SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, \
in that case the connection would be established as "open SHARING_LOCATION" would do before \
execute the command.

Type "<b>help open</b>" for more information about SHARING_LOCATION format."""


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
    def long_description(cls):
        comms = "\n".join(["    " + comm for comm in sorted(COMMANDS_INFO.keys())])
        return f"""\
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
{comms}"""

    @classmethod
    def synopsis(cls):
        return "help [COMMAND]"

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
    def long_description(cls):
        return f"""\
Exit from the interactive shell.

Open connections are automatically closed."""

    @classmethod
    def synopsis(cls):
        return """\
exit
quit
q"""

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
    def long_description(cls):
        return """\
Show (1) or hide (0) the packets sent and received to and from the server for any operation.

If no argument is given, toggle the packet tracing mode.
"""

    @classmethod
    def synopsis(cls):
        return """\
trace   [0 | 1]
t       [0 | 1]"""

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
                 CommandOptionInfo(None, param=Trace.T0[0][0], description=Trace.T0[1]),
                 CommandOptionInfo(None, param=Trace.T1[0][0], description=Trace.T1[1])
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
    def long_description(cls):
        pass

    @classmethod
    def synopsis(cls):
        return """\
verbose   [0 | 1 | 2 | 3 | 4]
v         [0 | 1 | 2 | 3 | 4]"""

    @classmethod
    def suggestions(cls, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_string(justification=15 + 6))
             for info in [
                 CommandOptionInfo(None, param=Verbose.V0[0][0], description=Verbose.V0[1]),
                 CommandOptionInfo(None, param=Verbose.V1[0][0], description=Verbose.V1[1]),
                 CommandOptionInfo(None, param=Verbose.V2[0][0], description=Verbose.V2[1]),
                 CommandOptionInfo(None, param=Verbose.V3[0][0], description=Verbose.V3[1]),
                 CommandOptionInfo(None, param=Verbose.V4[0][0], description=Verbose.V4[1]),
                 CommandOptionInfo(None, param=Verbose.V5[0][0], description=Verbose.V5[1]),
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
    def long_description(cls):
        return """\
Show the name of current local working directory.

The local working directory can be changed with the command <b>cd</b>."""

    @classmethod
    def synopsis(cls):
        return "pwd"

class Rpwd(RemoteSharingCommandInfo):

    @classmethod
    def name(cls):
        return "rpwd"

    @classmethod
    def short_description(cls):
        return "show the name of current remote working directory"

    @classmethod
    def long_description(cls):
        return f"""\
Show the name of current remote working directory.

The remote working directory can be changed with the command <b>rcd</b>."""

    @classmethod
    def synopsis(cls):
        return "rpwd"


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
    def long_description(cls):
        return """\
List content of the local DIR or the current local directory if no DIR is specified."""

    @classmethod
    def synopsis(cls):
        return "ls [OPTION]... [DIR]"

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
    def long_description(cls):
        return f"""\
List content of the remote DIR or the current remote directory if no DIR is specified."""

    @classmethod
    def synopsis(cls):
        return """\
rls [OPTION]... [DIR]
rls [OPTION]... [SHARING_LOCATION] [DIR]"""


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
            CommandOptionInfo(cls.MAX_DEPTH, "maximum display depth of tree", "depth")
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
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the local DIR or the current \
local directory if no DIR is specified."""

    @classmethod
    def synopsis(cls):
        return "tree [OPTION]... [DIR]"

class Rtree(BaseTreeCommandInfo, ListLocalAllCommandInfo, RemoteSharingCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rtree"

    @classmethod
    def short_description(cls):
        return "list remote directory contents in a tree-like format"

    @classmethod
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the remote DIR or the current \
remote directory if no DIR is specified"""

    @classmethod
    def synopsis(cls):
        return "tree [OPTION]... [DIR]"



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
    # LOCAL_CHANGE_DIRECTORY = "cd"
    # LOCAL_CREATE_DIRECTORY = "mkdir"
    # LOCAL_COPY = "cp"
    # LOCAL_MOVE = "mv"
    # LOCAL_REMOVE = "rm"
    # LOCAL_EXEC = "exec"
    # LOCAL_EXEC_SHORT = SPECIAL_COMMAND_MARK
    #
    Commands.REMOTE_CURRENT_DIRECTORY: Rpwd,
    Commands.REMOTE_LIST_DIRECTORY: Rls,
    Commands.REMOTE_LIST_DIRECTORY_ENHANCED: Rl,
    Commands.REMOTE_TREE_DIRECTORY: Rtree,
    # REMOTE_CHANGE_DIRECTORY = "rcd"
    # REMOTE_CREATE_DIRECTORY = "rmkdir"
    # REMOTE_COPY = "rcp"
    # REMOTE_MOVE = "rmv"
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

