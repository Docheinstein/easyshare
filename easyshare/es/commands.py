import os
from abc import abstractmethod, ABC
from typing import List, Callable, Union, Optional, Dict, Tuple, Type

from easyshare.args import KwArg, PositionalArgs, PRESENCE_PARAM
from easyshare.es.ui import StyledString
from easyshare.logging import get_logger
from easyshare.protocol import FileInfo
from easyshare.protocol import FTYPE_DIR, FTYPE_FILE
from easyshare.protocol import is_data_response
from easyshare.common import DIR_COLOR, FILE_COLOR
from easyshare.styling import fg
from easyshare.utils.os import ls
from easyshare.utils.str import rightof
from easyshare.utils.types import is_str

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
    return s.startswith(sp_comm) and \
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

CommandOptionInfo = Tuple[List[str], str]

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
    def options(cls) -> List[CommandOptionInfo]:
        return []

    @classmethod
    def examples(cls):
        return []

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

        options_aliases = []
        longest_option = 0
        i = 0

        while i < len(options):
            aliases, _ = options[i]
            options_aliases.append(_aliases_string(aliases))

            longest_option = max(
                longest_option,
                len(options_aliases[i])
            )
            i += 1

        log.d("Longest option string length: %d", longest_option)

        suggestions = []
        i = 0

        while i < len(options):
            _, desc = options[i]
            suggestions.append(StyledString(
                _aliases_and_desc_string(
                    aliases=options_aliases[i],
                    description=desc,
                    justification=longest_option,
                )
            ))
            i += 1

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
#
#
# class VerboseCommandInfo(CommandInfo):
#     V0 = CommandArgInfo(["0"], "error")
#     V1 = CommandArgInfo(["1"], "error / warning")
#     V2 = CommandArgInfo(["2"], "error / warning / info")
#     V3 = CommandArgInfo(["3"], "error / warning / info / verbose")
#     V4 = CommandArgInfo(["4"], "error / warning / info / verbose / debug")
#
#     def suggestions(self, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
#         return SuggestionsIntent(
#             [StyledString(c.args_help_str()) for c in [
#                 VerboseCommandInfo.V0,
#                 VerboseCommandInfo.V1,
#                 VerboseCommandInfo.V2,
#                 VerboseCommandInfo.V3,
#                 VerboseCommandInfo.V4]
#              ],
#             completion=False,
#             max_columns=1,
#         )
#
#


# ==================================================
# ============== COMMON DESCRIPTIONS ===============
# ==================================================

SHARING_LOCATION_IF_NOT_CONNECTED_DESC = """\
SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, \
in that case the connection would be established as "open SHARING_LOCATION" would do before \
execute the command.

See "help open" for more information about SHARING_LOCATION format."""


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

    def suggestions(self, token: str, line: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(_aliases_and_desc_string(
                    aliases=c[0],
                    description=c[1]
                )) for c in [
                    Trace.T0,
                    Trace.T1
                ]
             ],
            completion=False,
            max_columns=1,
        )

# xLS

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
            (cls.SORT_BY_SIZE, "sort by size"),
            (cls.REVERSE, "reverse sort order"),
            (cls.GROUP, "group by file type"),
            (cls.SHOW_ALL, "show hidden files too"),
            (cls.SHOW_SIZE, "show files size"),
            (cls.SHOW_DETAILS, "show more details")
        ]

    def kwargs_specs(self) -> Optional[List[KwArg]]:
        return [
            (Ls.SORT_BY_SIZE, PRESENCE_PARAM),
            (Ls.REVERSE, PRESENCE_PARAM),
            (Ls.GROUP, PRESENCE_PARAM),
            (Ls.SHOW_ALL, PRESENCE_PARAM),
            (Ls.SHOW_DETAILS, PRESENCE_PARAM),
            (Ls.SHOW_SIZE, PRESENCE_PARAM),
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
List content of the local FILE or the current local directory if no FILE is specified."""

    @classmethod
    def synopsis(cls):
        return "ls [OPTION]... [FILE]"

class Rls(BaseLsCommandInfo, ListLocalAllCommandInfo):
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
List content of the remote FILE or the current remote directory if no FILE is specified.

{SHARING_LOCATION_IF_NOT_CONNECTED_DESC}"""

    @classmethod
    def synopsis(cls):
        return """\
rls [OPTION]... [FILE]
rls [OPTION]... [SHARING_LOCATION] [FILE]"""


#
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

def _aliases_string(aliases: List[str]):
    return ', '.join(aliases)

def _aliases_and_desc_string(aliases: Union[str, List[str]], description: str, justification: int = 0,):
    if not is_str(aliases):
        aliases = _aliases_string(aliases)

    return f"{aliases.ljust(justification)}      {description}"


COMMANDS_INFO: Dict[str, Type[CommandInfo]] = {
    Commands.HELP: Help,
    Commands.HELP_SHORT: Help,
    Commands.EXIT: Exit,
    Commands.QUIT: Exit,
    Commands.QUIT_SHORT: Exit,

    Commands.TRACE: Trace,
    Commands.TRACE_SHORT: Trace,
    #
    # VERBOSE = "verbose"
    # VERBOSE_SHORT = "v"
    #
    # LOCAL_CURRENT_DIRECTORY = "pwd"
    Commands.LOCAL_LIST_DIRECTORY: Ls,
    # LOCAL_LIST_DIRECTORY_ENHANCED = "l"
    # LOCAL_TREE_DIRECTORY = "tree"
    # LOCAL_CHANGE_DIRECTORY = "cd"
    # LOCAL_CREATE_DIRECTORY = "mkdir"
    # LOCAL_COPY = "cp"
    # LOCAL_MOVE = "mv"
    # LOCAL_REMOVE = "rm"
    # LOCAL_EXEC = "exec"
    # LOCAL_EXEC_SHORT = SPECIAL_COMMAND_MARK
    #
    # REMOTE_CURRENT_DIRECTORY = "rpwd"
    Commands.REMOTE_LIST_DIRECTORY: Rls
    # REMOTE_LIST_DIRECTORY_ENHANCED = "rl"
    # REMOTE_TREE_DIRECTORY = "rtree"
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

