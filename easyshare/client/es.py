import enum
import os
import random
import shlex
import ssl
import sys
import readline
import time
from abc import ABC, abstractmethod
from getpass import getpass
from math import ceil
from stat import S_ISDIR, S_ISREG
from typing import Optional, Callable, List, Dict, Type, Union, Tuple

import Pyro4
from Pyro4 import socketutil
from Pyro4.errors import ConnectionClosedError, PyroError

from easyshare.client.connection import Connection
from easyshare.client.discover import Discoverer
from easyshare.client.errors import ClientErrors
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_DIR, FTYPE_FILE, FileType
from easyshare.protocol.iserver import IServer
from easyshare.protocol.response import Response, is_error_response, is_success_response, is_data_response
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.sharinginfo import SharingInfo
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_NAME_CLIENT, APP_NAME_CLIENT_SHORT, APP_VERSION, DEFAULT_DISCOVER_PORT, DIR_COLOR, \
    FILE_COLOR, PROGRESS_COLOR, DONE_COLOR
from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import i, d, w, init_logging, v, VERBOSITY_VERBOSE, get_verbosity, VERBOSITY_MAX, \
    VERBOSITY_NONE, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO, VERBOSITY_DEBUG, e
from easyshare.shared.progress import FileProgressor
from easyshare.shared.ssl import get_ssl_context
from easyshare.shared.trace import init_tracing, is_tracing_enabled
from easyshare.socket.tcp import SocketTcpOut
from easyshare.tree.tree import TreeNodeDict, TreeRenderPostOrder
from easyshare.utils.app import eprint, terminate, abort
from easyshare.utils.colors import init_colors, Color, red, fg, styled
from easyshare.utils.env import terminal_size
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.obj import values, items
from easyshare.utils.str import unprefix, satisfy, leftof, rightof
from easyshare.utils.types import to_int, to_bool, str_to_bool, bool_to_str, is_bool
from easyshare.utils.os import ls, size_str, rm, tree, mv, cp, is_hidden

# ==================================================================


APP_INFO = APP_NAME_CLIENT + " (" + APP_NAME_CLIENT_SHORT + ") v. " + APP_VERSION


# === HELPS ===


HELP_APP = """\
cd      <path>      |   change local directory
exit                |   exit shell
get     <file>      |   download file or folder
help                |   print command list
ls                  |   list local directory
mkdir   <folder>    |   create local directory
open    <sharing>   |   connect to a server's sharing
put     <file>      |   upload file or folder
pwd                 |   print local directory name
rcd     <path>      |   change remote directory
rls                 |   list remote directory
rmkdir  <folder>    |   create remote directory
rpwd                |   print remote directory name
scan    [timeout]   |   scan the network for sharings"""

HELP_COMMANDS = """\
cd      <path>      |   change local directory
exit                |   exit shell
get     <file>      |   download file or folder
help                |   print command list
ls                  |   list local directory
mkdir   <folder>    |   create local directory
open    <sharing>   |   connect to a server's sharing
put     <file>      |   upload file or folder
pwd                 |   print local directory name
rcd     <path>      |   change remote directory
rls                 |   list remote directory
rmkdir  <folder>    |   create remote directory
rpwd                |   print remote directory name
scan    [timeout]   |   scan the network for sharings"""


# === ARGUMENTS ===


class ClientArguments:
    TRACE =     ["-t", "--trace"]
    VERBOSE =   ["-v", "--verbose"]
    PORT =      ["-p", "--port"]
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]
    NO_COLOR =  ["--no-color"]


# === COMMANDS ===


class StyledString:
    def __init__(self, string: str, styled_string: str = None):
        self.string = string
        self.styled_string = styled_string or string

    def __str__(self):
        return self.string


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


class CommandArg:
    def __init__(self, arg_aliases: List[str], arg_help: str):
        self.aliases = arg_aliases
        self.help = arg_help

    def args_str(self) -> str:
        return ", ".join(self.aliases)

    def args_help_str(self, justify: int = 0):
        return "{}    {}".format(
            self.args_str().ljust(justify),
            self.help
        )

    def __str__(self):
        return self.args_help_str()


class CommandInfo:
    def __init__(self):
        pass

    @classmethod
    def args(cls) -> List[CommandArg]:
        return []

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
        return None


class ArgsCommandInfo(CommandInfo):

    @classmethod
    def args(cls) -> List[CommandArg]:
        if not hasattr(cls, "ARGS"):
            setattr(cls, "ARGS", [attr for attr in values(cls) if isinstance(attr, CommandArg)])
        return getattr(cls, "ARGS")

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
        d("Token: %s", token)
        if not token.startswith("-"):
            return None

        d("Computing args suggestions")

        longest_args_names = 0

        for comm_args in cls.args():
            longest_args_names = max(
                longest_args_names,
                len(comm_args.args_str())
            )

        suggestions = [StyledString(comm_args.args_help_str(justify=longest_args_names)) for comm_args in cls.args()]

        return SuggestionsIntent(suggestions,
                                 completion=False,
                                 max_columns=1)


class ListCommandInfo(ArgsCommandInfo, ABC):
    @classmethod
    @abstractmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        pass

    @classmethod
    @abstractmethod
    def list(cls, token: str, line: str, client: 'Client') -> List[FileInfo]:
        pass

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:

        suggestions_intent = super().suggestions(token, line, client)
        if suggestions_intent:
            return suggestions_intent

        # pattern = rightof(line, " ", from_end=True)
        # path_dir, path_trail = os.path.split(os.path.join(os.getcwd(), pattern))

        # d("pattern: %s", pattern)
        # d("path_dir: %s", path_dir)
        # d("path_trail: %s", path_trail)

        suggestions = []
        for finfo in cls.list(token, line, client):
            d("finfo: %s", finfo)

            fname = finfo.get("name")

            if not cls.display_path_filter(finfo):
                d("%s doesn't pass the filter", fname)
                continue

            _, fname_tail = os.path.split(fname)

            if not fname_tail.startswith(token):
                continue

            # f_full = os.path.join(path_dir, f)

            # d("f_full: %s", f_full)

            if finfo.get("ftype") == FTYPE_DIR:
                # Append a dir, with a trailing / so that the next
                # suggestion can continue to traverse the file system
                ff = fname_tail + "/"
                suggestions.append(StyledString(ff, fg(ff, color=DIR_COLOR)))
            else:
                # Append a file, with a trailing space since there
                # is no need to traverse the file system
                ff = fname_tail + " "
                suggestions.append(StyledString(ff, fg(ff, color=FILE_COLOR)))

        # def space_after_completion(suggestion: str) -> bool:
        #     return not suggestion.endswith(os.path.sep)

        # print("suggestions: ", [str(s) for s in suggestions])
        return SuggestionsIntent(suggestions,
                                 completion=True,
                                 space_after_completion=False)


class ListLocalCommandInfo(ListCommandInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client: 'Client') -> List[FileInfo]:
        d("List on token = '%s', line = '%s'", token, line)
        pattern = rightof(line, " ", from_end=True)
        path_dir, path_trail = os.path.split(os.path.join(os.getcwd(), pattern))
        d("ls-ing on %s", path_dir)
        return ls(path_dir)


class ListRemoteCommandInfo(ListCommandInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client: 'Client') -> List[FileInfo]:
        if not client or not client.is_connected():
            w("Cannot list() on a non connected client")
            return []

        d("List remotely on token = '%s', line = '%s'", token, line)
        pattern = rightof(line, " ", from_end=True)
        path_dir, path_trail = os.path.split(pattern)

        d("rls-ing on %s", pattern)
        resp = client.connection.rls(sort_by=["name"], path=path_dir)

        if not is_data_response(resp):
            w("Unable to retrieve a valid response for rls")
            return []

        return resp.get("data")


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


class ListLocalAllCommandInfo(ListLocalCommandInfo, ListAllFilter):
    pass


class ListLocalDirsCommandInfo(ListLocalCommandInfo, ListDirsFilter):
    pass


class ListLocalFilesCommandInfo(ListLocalCommandInfo, ListFilesFilter):
    pass


class ListRemoteAllCommandInfo(ListRemoteCommandInfo, ListAllFilter):
    pass


class ListRemoteDirsCommandInfo(ListRemoteCommandInfo, ListDirsFilter):
    pass


class ListRemoteFilesCommandInfo(ListRemoteCommandInfo, ListFilesFilter):
    pass



class VerboseCommandInfo(CommandInfo):
    V0 = CommandArg(["0"], "error")
    V1 = CommandArg(["1"], "error / warning")
    V2 = CommandArg(["2"], "error / warning / info")
    V3 = CommandArg(["3"], "error / warning / info / verbose")
    V4 = CommandArg(["4"], "error / warning / info / verbose / debug")

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(c.args_help_str()) for c in [
                VerboseCommandInfo.V0,
                VerboseCommandInfo.V1,
                VerboseCommandInfo.V2,
                VerboseCommandInfo.V3,
                VerboseCommandInfo.V4]
             ],
            completion=False,
            max_columns=1,
        )


class TraceCommandInfo(CommandInfo):
    T0 = CommandArg(["0"], "enable packet tracing")
    T1 = CommandArg(["1"], "disable packet tracing")

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(c.args_help_str()) for c in [
                TraceCommandInfo.T0,
                TraceCommandInfo.T1]
             ],
            completion=False,
            max_columns=1,
        )


class BaseLsCommandInfo(ArgsCommandInfo):
    SORT_BY_SIZE = CommandArg(["-s", "--sort-size"], "Sort by size")
    REVERSE = CommandArg(["-r", "--reverse"], "Reverse sort order")
    GROUP = CommandArg(["-g", "--group"], "Group by file type")
    SIZE = CommandArg(["-S"], "Show file size")
    DETAILS = CommandArg(["-l"], "Show all the details")


class LsCommandInfo(BaseLsCommandInfo, ListLocalAllCommandInfo):
    pass


class RlsCommandInfo(BaseLsCommandInfo, ListRemoteAllCommandInfo):
    pass


class BaseTreeCommandInfo(ArgsCommandInfo):
    SORT_BY_SIZE = CommandArg(["-s", "--sort-size"], "Sort by size")
    REVERSE = CommandArg(["-r", "--reverse"], "Reverse sort order")
    GROUP = CommandArg(["-g", "--group"], "Group by file type")
    MAX_DEPTH = CommandArg(["-d", "--depth"], "Maximum depth")
    SIZE = CommandArg(["-S"], "Show file size")
    DETAILS = CommandArg(["-l"], "Show all the details")


class TreeCommandInfo(BaseTreeCommandInfo, ListLocalAllCommandInfo):
    pass


class RtreeCommandInfo(BaseTreeCommandInfo, ListRemoteAllCommandInfo):
    pass


class GetCommandInfo(ArgsCommandInfo):
    YES_TO_ALL = CommandArg(["-Y", "--yes"], "Always overwrite existing files")
    NO_TO_ALL = CommandArg(["-N", "--no"], "Never overwrite existing files")


class PutCommandInfo(ArgsCommandInfo):
    YES_TO_ALL = CommandArg(["-Y", "--yes"], "Always overwrite existing files")
    NO_TO_ALL = CommandArg(["-N", "--no"], "Never overwrite existing files")


class ScanCommandInfo(ArgsCommandInfo):
    DETAILS = CommandArg(["-l"], "Show all the details")


class Commands:
    HELP = "help"
    EXIT = "exit"

    TRACE = "trace"
    TRACE_SHORT = "t"

    VERBOSE = "verbose"
    VERBOSE_SHORT = "v"

    LOCAL_CURRENT_DIRECTORY = "pwd"
    LOCAL_LIST_DIRECTORY = "ls"
    LOCAL_TREE_DIRECTORY = "tree"
    LOCAL_CHANGE_DIRECTORY = "cd"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_COPY = "cp"
    LOCAL_MOVE = "mv"
    LOCAL_REMOVE = "rm"

    REMOTE_CURRENT_DIRECTORY = "rpwd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_TREE_DIRECTORY = "rtree"
    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_COPY = "rcp"
    REMOTE_MOVE = "rmv"
    REMOTE_REMOVE = "rrm"

    SCAN = "scan"
    OPEN = "open"
    CLOSE = "close"

    GET = "get"
    PUT = "put"

    INFO = "info"
    PING = "ping"


COMMANDS_INFO: Dict[str, Type[CommandInfo]] = {
    Commands.HELP: CommandInfo,
    Commands.EXIT: CommandInfo,

    Commands.TRACE: TraceCommandInfo,
    Commands.TRACE_SHORT: TraceCommandInfo,

    Commands.VERBOSE: VerboseCommandInfo,
    Commands.VERBOSE_SHORT: VerboseCommandInfo,


    Commands.LOCAL_CURRENT_DIRECTORY: CommandInfo,
    Commands.LOCAL_LIST_DIRECTORY: LsCommandInfo,   # listlocal
    Commands.LOCAL_TREE_DIRECTORY: TreeCommandInfo, # listlocale
    Commands.LOCAL_CHANGE_DIRECTORY: ListLocalDirsCommandInfo,
    Commands.LOCAL_CREATE_DIRECTORY: ListLocalDirsCommandInfo,
    Commands.LOCAL_COPY: ListLocalAllCommandInfo,
    Commands.LOCAL_MOVE: ListLocalAllCommandInfo,
    Commands.LOCAL_REMOVE: ListLocalAllCommandInfo,


    Commands.REMOTE_CURRENT_DIRECTORY: CommandInfo,
    Commands.REMOTE_LIST_DIRECTORY: RlsCommandInfo,
    Commands.REMOTE_TREE_DIRECTORY: RtreeCommandInfo,
    Commands.REMOTE_CHANGE_DIRECTORY: ListRemoteDirsCommandInfo,
    Commands.REMOTE_CREATE_DIRECTORY: ListRemoteDirsCommandInfo,
    Commands.REMOTE_COPY: ListRemoteAllCommandInfo,
    Commands.REMOTE_MOVE: ListRemoteAllCommandInfo,
    Commands.REMOTE_REMOVE: ListRemoteAllCommandInfo,


    Commands.SCAN: ScanCommandInfo,
    Commands.OPEN: CommandInfo,
    Commands.CLOSE: CommandInfo,

    Commands.GET: GetCommandInfo,
    Commands.PUT: PutCommandInfo,

    Commands.INFO: CommandInfo,
    Commands.PING: CommandInfo,
}

SHELL_COMMANDS = values(Commands)

CLI_COMMANDS = [
    Commands.SCAN,
    Commands.OPEN,
    Commands.GET,
    Commands.INFO,
]

# === COMMANDS ARGUMENTS ===


class LsArguments:
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]
    SIZE = ["-S"]
    DETAILS = ["-l"]
    ALL = ["-a", "--all"]


class TreeArguments:
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]
    MAX_DEPTH = ["-d", "--depth"]
    SIZE = ["-S"]


class OpenArguments:
    TIMEOUT = ["-T", "--timeout"]


class ScanArguments:
    TIMEOUT = ["-T", "--timeout"]
    DETAILS = ["-l"]


class GetArguments:
    YES_TO_ALL = ["-Y", "--yes"]
    NO_TO_ALL = ["-N", "--no"]


class PutArguments:
    YES_TO_ALL = ["-Y", "--yes"]
    NO_TO_ALL = ["-N", "--no"]


# === MISC ===

class GetMode(enum.Enum):
    FILES = "files"
    SHARING = "sharing"

# === ERRORS ===


class ErrorsStrings:
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SHARING_NOT_FOUND = "Sharing not found"
    SERVER_NOT_FOUND = "Server not found"
    INVALID_PATH = "Invalid path"
    INVALID_TRANSACTION = "Invalid transaction"
    NOT_ALLOWED = "Not allowed"
    AUTHENTICATION_FAILED = "Authentication failed"
    INTERNAL_SERVER_ERROR = "Internal server error"
    NOT_WRITABLE = "Cannot perform the action on a readonly sharing"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected server response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"


ERRORS_STRINGS_MAP = {
    ServerErrors.ERROR: ErrorsStrings.ERROR,
    ServerErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ServerErrors.NOT_IMPLEMENTED: ErrorsStrings.NOT_IMPLEMENTED,
    ServerErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ServerErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ServerErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ServerErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ServerErrors.INVALID_TRANSACTION: ErrorsStrings.INVALID_TRANSACTION,
    ServerErrors.NOT_ALLOWED: ErrorsStrings.NOT_ALLOWED,
    ServerErrors.AUTHENTICATION_FAILED: ErrorsStrings.AUTHENTICATION_FAILED,
    ServerErrors.INTERNAL_SERVER_ERROR: ErrorsStrings.INTERNAL_SERVER_ERROR,

    ClientErrors.COMMAND_NOT_RECOGNIZED: ErrorsStrings.COMMAND_NOT_RECOGNIZED,
    ClientErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ClientErrors.INVALID_PARAMETER_VALUE: ErrorsStrings.INVALID_PARAMETER_VALUE,
    ClientErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ClientErrors.UNEXPECTED_SERVER_RESPONSE: ErrorsStrings.UNEXPECTED_SERVER_RESPONSE,
    ClientErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ClientErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ClientErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ClientErrors.SERVER_NOT_FOUND: ErrorsStrings.SERVER_NOT_FOUND,
    ClientErrors.IMPLEMENTATION_ERROR: ErrorsStrings.IMPLEMENTATION_ERROR,
    ClientErrors.CONNECTION_ERROR: ErrorsStrings.CONNECTION_ERROR,
}


def error_string(error_code: int) -> str:
    return ERRORS_STRINGS_MAP.get(error_code, ErrorsStrings.ERROR)


def print_error(error_code: int):
    eprint(error_string(error_code))


def print_response_error(resp: Response):
    if is_error_response(resp):
        print_error(resp["error"])


def print_tabulated(strings: List[StyledString], max_columns: int = None):
    term_cols, _ = terminal_size()

    longest_string_length = len(str(max(strings, key=lambda ss: len(str(ss)))))
    min_col_width = longest_string_length + 2

    max_allowed_cols = max_columns if max_columns else 50
    max_fillable_cols = term_cols // min_col_width

    display_cols = min(max_allowed_cols, max_fillable_cols)
    display_rows = ceil(len(strings) / display_cols)

    d("term_cols %d", term_cols)
    d("longest_match_length %d", longest_string_length)
    d("min_col_width %d", min_col_width)
    d("max_allowed_cols %d", max_allowed_cols)
    d("max_fillable_cols %d", max_fillable_cols)
    d("len_strings %d", len(strings))
    d("display_rows %d", display_rows)
    d("display_cols %d", display_cols)

    for r in range(0, display_rows):
        print_row = ""

        for c in range(0, display_cols):
            idx = r + c * display_rows
            if idx < len(strings):
                # Add the styled string;
                # We have to justify keeping the non-printable
                # characters in count
                ss = strings[idx]

                justification = min_col_width + len(ss.styled_string) - len(ss.string)
                print_row += ss.styled_string.ljust(justification)
        print(print_row)


# ==================================================================


class Client:
    def __init__(self, server_discover_port: int):
        self.connection: Optional[Connection] = None

        self._server_discover_port = server_discover_port

        self._command_dispatcher: Dict[str, Callable[[Args], None]] = {
            Commands.TRACE: self.trace,
            Commands.TRACE_SHORT: self.trace,
            Commands.VERBOSE: self.verbose,
            Commands.VERBOSE_SHORT: self.verbose,

            Commands.LOCAL_CHANGE_DIRECTORY: self.cd,
            Commands.LOCAL_LIST_DIRECTORY: self.ls,
            Commands.LOCAL_TREE_DIRECTORY: self.tree,
            Commands.LOCAL_CREATE_DIRECTORY: self.mkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self.pwd,
            Commands.LOCAL_REMOVE: self.rm,
            Commands.LOCAL_MOVE: self.mv,
            Commands.LOCAL_COPY: self.cp,

            Commands.REMOTE_CHANGE_DIRECTORY: self.rcd,
            Commands.REMOTE_LIST_DIRECTORY: self.rls,
            Commands.REMOTE_TREE_DIRECTORY: self.rtree,
            Commands.REMOTE_CREATE_DIRECTORY: self.rmkdir,
            Commands.REMOTE_CURRENT_DIRECTORY: self.rpwd,
            Commands.REMOTE_REMOVE: self.rrm,
            Commands.REMOTE_MOVE: self.rmv,
            Commands.REMOTE_COPY: self.rcp,

            Commands.SCAN: self.scan,
            Commands.OPEN: self.open,
            Commands.CLOSE: self.close,

            Commands.GET: self.get,
            Commands.PUT: self.put,

            Commands.INFO: self.info,

            Commands.PING: self.ping,
        }

    def execute_command(self, command: str, args: Args) -> bool:
        if command not in self._command_dispatcher:
            return False

        d("Client: handling command %s (%s)", command, args)
        self._command_dispatcher[command](args)
        return True

    def is_connected(self):
        return self.connection and self.connection.is_connected()

    # === LOCAL COMMANDS ===

    def trace(self, args: Args):
        enable = to_int(args.get_param())

        if enable is None:
            # Toggle tracing if no parameter is provided
            enable = not is_tracing_enabled()

        i(">> TRACE (%d)", enable)

        init_tracing(enable)

        print("Tracing = {:d}{}".format(
            enable,
            " (enabled)" if enable else " (disabled)"
        ))

    def verbose(self, args: Args):
        verbosity = to_int(args.get_param())

        if verbosity is None:
            # Increase verbosity (or disable if is already max)
            verbosity = (get_verbosity() + 1) % (VERBOSITY_MAX + 1)

        i(">> VERBOSE (%d)", verbosity)

        init_logging(verbosity)


        VERBOSITY_EXPLANATION_MAP = {
            VERBOSITY_NONE: " (disabled)",
            VERBOSITY_ERROR: " (error)",
            VERBOSITY_WARNING: " (error / warn)",
            VERBOSITY_INFO: " (error / warn / info)",
            VERBOSITY_VERBOSE: " (error / warn / info / verbose)",
            VERBOSITY_DEBUG: " (error / warn / info / verbose / debug)",
        }

        if verbosity not in VERBOSITY_EXPLANATION_MAP:
            verbosity = max(min(verbosity, VERBOSITY_DEBUG), VERBOSITY_NONE)

        print("Verbosity = {:d}{}".format(
            verbosity,
            VERBOSITY_EXPLANATION_MAP.get(verbosity, "")
        ))

    def cd(self, args: Args):
        directory = args.get_param(default="/")

        i(">> CD %s", directory)

        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            print_error(ClientErrors.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def ls(self, args: Args):
        path = args.get_param()
        if not path:
            path = os.getcwd()

        sort_by = ["name"]
        reverse = LsCommandInfo.REVERSE.aliases in args

        if LsArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if LsArguments.GROUP in args:
            sort_by.append("ftype")

        i(">> LS (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        ls_result = ls(path, sort_by=sort_by, reverse=reverse)
        if ls_result is None:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

        Client._print_list_files_info(
            ls_result,
            show_size=LsArguments.SIZE in args or LsArguments.DETAILS in args,
            show_file_type=LsArguments.DETAILS in args,
            show_hidden=LsArguments.ALL in args,
            compact=LsArguments.DETAILS not in args
        )

    def tree(self, args: Args):
        sort_by = ["name"]
        reverse = TreeArguments.REVERSE in args

        if TreeArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if TreeArguments.GROUP in args:
            sort_by.append("ftype")

        # FIXME: max_depth = 0
        max_depth = to_int(args.get_param(TreeArguments.MAX_DEPTH))

        i(">> TREE (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        tree_root = tree(os.getcwd(), sort_by=sort_by, reverse=reverse, max_depth=max_depth)

        if tree_root is None:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

        Client._print_tree_files_info(tree_root,
                                      max_depth=max_depth,
                                      show_size=TreeArguments.SIZE in args)

    def mkdir(self, args: Args):
        directory = args.get_param()

        if not directory:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> MKDIR " + directory)

        try:
            os.mkdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def pwd(self, _: Args):
        i(">> PWD")

        try:
            print(os.getcwd())
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def rm(self, args: Args):
        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RM %s", paths)

        def handle_rm_error(err):
            eprint(err)

        for path in paths:
            rm(path, error_callback=handle_rm_error)

    def mv(self, args: Args):
        """
        mv <src>... <dest>

        A1  At least two parameters
        A2  If a <src> doesn't exist => IGNORES it

        2 args:
        B1  If <dest> exists
            B1.1    If type of <dest> is DIR => put <src> into <dest> anyway

            B1.2    If type of <dest> is FILE
                B1.2.1  If type of <src> is DIR => ERROR
                B1.2.2  If type of <src> is FILE => OVERWRITE
        B2  If <dest> doesn't exist => preserve type of <src>

        3 args:
        C1  if <dest> exists => must be a dir
        C2  If <dest> doesn't exist => ERROR

        """
        mv_args = args.get_params()
        args_count = len(mv_args)

        if not mv_args or args_count < 2:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = mv_args.pop()

        # C1/C2 check: with 3+ arguments
        if args_count >= 3:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest):
                eprint("'%s' must be an existing directory", dest)
                return

        # Every other constraint is well handled by shutil.move()
        errors = []

        for src in mv_args:
            v(">> MV <%s> <%s>", src, dest)
            try:
                mv(src, dest)
            except Exception as ex:
                errors.append(str(ex))

        if errors:
            e("%d errors occurred", len(errors))

        for err in errors:
            eprint(err)


    def cp(self, args: Args):

        cp_args = args.get_params()
        args_count = len(cp_args)

        if not cp_args or args_count < 2:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = cp_args.pop()

        # C1/C2 check: with 3+ arguments
        if args_count >= 3:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest):
                eprint("'%s' must be an existing directory", dest)
                return

        # Every other constraint is well handled by shutil.move()
        errors = []

        for src in cp_args:
            v(">> CP <%s> <%s>", src, dest)
            try:
                cp(src, dest)
            except Exception as ex:
                errors.append(str(ex))

        if errors:
            e("%d errors occurred", len(errors))

        for err in errors:
            eprint(err)

    # === REMOTE COMMANDS ===

    # RPWD

    def rpwd(self, _: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.rpwd())

    def rcd(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        directory = args.get_param(default="/")

        i(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_success_response(resp):
            v("Successfully RCDed")
        else:
            self._handle_error_response(resp)

    def rls(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        path = args.get_param()
        sort_by = ["name"]
        reverse = LsArguments.REVERSE in args

        if LsArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if LsArguments.GROUP in args:
            sort_by.append("ftype")

        i(">> RLS (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        resp = self.connection.rls(sort_by, reverse=reverse, path=path)

        if not is_data_response(resp):
            self._handle_error_response(resp)
            return

        Client._print_list_files_info(
            resp.get("data"),
            show_size=LsArguments.SIZE in args or LsArguments.DETAILS in args,
            show_file_type=LsArguments.DETAILS in args,
            show_hidden=LsArguments.ALL in args,
            compact=LsArguments.DETAILS not in args
        )


    def rtree(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        sort_by = ["name"]
        reverse = TreeArguments.REVERSE in args

        if TreeArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if TreeArguments.GROUP in args:
            sort_by.append("ftype")

        # FIXME: max_depth = 0
        max_depth = to_int(args.get_param(TreeArguments.MAX_DEPTH))

        i(">> RTREE (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        resp = self.connection.rtree(sort_by, reverse=reverse, depth=max_depth)

        if not is_data_response(resp):
            self._handle_error_response(resp)
            return

        Client._print_tree_files_info(resp.get("data"),
                                      max_depth=max_depth,
                                      show_size=TreeArguments.SIZE in args)

    def rmkdir(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        directory = args.get_param()

        if not directory:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RMKDIR " + directory)

        resp = self.connection.rmkdir(directory)
        if is_success_response(resp):
            v("Successfully RMKDIRed")
            pass
        else:
            self._handle_error_response(resp)

    def rrm(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RRM %s ", paths)

        resp = self.connection.rrm(paths)
        if is_success_response(resp):
            v("Successfully RRMed")
            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rrm", len(errors))
                    for err in errors:
                        eprint(err)
        else:
            self._handle_error_response(resp)

    def rcp(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = paths.pop()

        if not dest or not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RCP %s -> %s", str(paths), dest)

        resp = self.connection.rcp(paths, dest)
        if is_success_response(resp):
            v("Successfully RCPed")

            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rcp", len(errors))
                    for err in errors:
                        eprint(err)

        else:
            self._handle_error_response(resp)

    def rmv(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = paths.pop()

        if not dest or not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RMV %s -> %s", str(paths), dest)

        resp = self.connection.rmv(paths, dest)
        if is_success_response(resp):
            v("Successfully RMVed")

            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rmv", len(errors))
                    for err in errors:
                        eprint(err)

        else:
            self._handle_error_response(resp)


    def open(self, args: Args) -> bool:
        #                    |------sharing_location-----|
        # open <sharing_name>[@<hostname> | @<ip>[:<port>]]
        #      |_________________________________________|
        #               sharing specifier

        sharing_specifier = args.get_param()

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return False

        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        sharing_name, _, sharing_location = sharing_specifier.partition("@")

        i(">> OPEN %s%s (timeout = %d)",
          sharing_name,
          "@{}".format(sharing_location) if sharing_location else "",
          timeout)

        sharing_info, server_info = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            ftype=FTYPE_DIR,
            timeout=timeout
        )

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            d("Creating new connection with %s", server_info.get("uri"))
            self.connection = Connection(server_info)
        else:
            d("Reusing existing connection with %s", server_info.get("uri"))

        passwd = None

        # Ask the password if the sharing is protected by auth
        if sharing_info.get("auth"):
            v("Sharing '%s' is protected by password", sharing_name)
            passwd = getpass()

        # Actually send OPEN

        resp = self.connection.open(sharing_name, passwd)
        if is_success_response(resp):
            v("Successfully connected to %s:%d",
              server_info.get("ip"), server_info.get("port"))
            return True
        else:
            self._handle_error_response(resp)
            self.close()
            return False

    def close(self, _: Optional[Args] = None):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> CLOSE")

        self.connection.close()  # async call
        self.connection = None   # Invalidate connection

    def scan(self, args: Args):
        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        show_details = ScanArguments.DETAILS in args

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        i(">> SCAN (timeout = %d)", timeout)

        servers_found = 0

        def response_handler(client: Endpoint,
                             server_info: ServerInfo) -> bool:
            nonlocal servers_found

            d("Handling DISCOVER response from %s\n%s", str(client), str(server_info))
            # Print as soon as they come

            if not servers_found:
                i("======================")
            else:
                print("")

            print("{} ({}:{})".format(
                server_info.get("name"),
                server_info.get("ip"),
                server_info.get("port")))


            print(Client._sharings_string(server_info.get("sharings"),
                                          details=show_details))

            servers_found += 1

            return True     # Go ahead

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        i("======================")

    def info(self, args: Args):
        # Can be done either
        # 1. If connected to a server: we already have the server info
        # 2. If not connected to a server: we have to fetch the server info

        # Without parameter it means we are trying to see the info of the
        # current connection
        # With a paremeter it means we are trying to see the info of a server
        # The param should be <hostname> | <ip[:port]>

        def print_server_info(server_info: ServerInfo):
            print(
                "Name: {}\n"
                "IP: {}\n"
                "Port: {}\n"
                "SSL: {}\n"
                "Sharings\n{}"
                .format(
                    server_info.get("name"),
                    server_info.get("ip"),
                    server_info.get("port"),
                    server_info.get("ssl"),
                    Client._sharings_string(server_info.get("sharings"))
                )
            )

        if self.is_connected():
            # Connected, print current server info
            d("Info while connected, printing current server info")
            print_server_info(self.connection.server_info)
        else:
            # Not connected, we need a parameter that specifies the server
            server_specifier = args.get_param()

            if not server_specifier:
                e("Server specifier not found")
                print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
                return

            i(">> INFO %s", server_specifier)

            server_info: ServerInfo = self._discover_server(
                location=server_specifier
            )

            if not server_info:
                print_error(ClientErrors.SERVER_NOT_FOUND)
                return False

            # Server info retrieved successfully
            print_server_info(server_info)

    def ping(self, _: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        resp = self.connection.ping()
        if is_data_response(resp) and resp.get("data") == "pong":
            print("Connection is UP")
        else:
            print("Connection is DOWN")



    def put_files(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        files = args.get_params(default=[])

        i(">> PUT [files] %s", files)
        self._do_put(self.connection, files, args)


    def put_sharing(self, args: Args):
        if self.is_connected():
            # We should not reach this point if we are connected to a sharing
            print_error(ClientErrors.IMPLEMENTATION_ERROR)
            return

        params = args.get_params()
        sharing_specifier = params.pop(0)

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        sharing_name, _, sharing_location = sharing_specifier.rpartition("@")

        if not sharing_name:
            # if @ is not found, rpartition put the entire string on
            # the last element of th tuple
            sharing_name = sharing_location
            sharing_location = None

        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        # We have to perform a discover

        sharing_info, server_info = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            timeout=timeout
        )

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        d("Creating new temporary connection with %s", server_info.get("uri"))
        connection = Connection(server_info)

        # FIXME: refactor - introduce password in the method

        # Open a temporary connection

        v("Opening temporary connection")
        open_response = connection.open(sharing_name)

        if not is_success_response(open_response):
            w("Cannot open connection; aborting")
            print_response_error(open_response)
            return

        files = ["."] if not params else params
        i(">> PUT [sharing] %s %s", sharing_name)
        self._do_put(connection, files, args)

        # Close connection
        d("Closing temporary connection")
        connection.close()

    def get_files(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        files = args.get_params(default=[])

        i(">> GET [files] %s", files)
        self._do_get(self.connection, files, args)

    def get_sharing(self, args: Args):
        if self.is_connected():
            # We should not reach this point if we are connected to a sharing
            print_error(ClientErrors.IMPLEMENTATION_ERROR)
            return

        params = args.get_params()
        sharing_specifier = params.pop(0)

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        sharing_name, _, sharing_location = sharing_specifier.rpartition("@")

        if not sharing_name:
            # if @ is not found, rpartition put the entire string on
            # the last element of th tuple
            sharing_name = sharing_location
            sharing_location = None

        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        # We have to perform a discover

        sharing_info, server_info = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            timeout=timeout
        )

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        d("Creating new temporary connection with %s", server_info.get("uri"))
        connection = Connection(server_info)

        # Open connection

        v("Opening temporary connection")
        open_response = connection.open(sharing_name)

        if not is_success_response(open_response):
            w("Cannot open connection; aborting")
            print_response_error(open_response)
            return

        files = ["."] if not params else params
        i(">> GET [sharing] %s %s", sharing_name)
        self._do_get(connection, files, args)

        # Close connection
        d("Closing temporary connection")
        connection.close()

    def _do_put(self,
                connection: Connection,
                files: List[str],
                args: Args):
        if not connection.is_connected():
            e("Connection must be opened for do GET")
            return

        if len(files) == 0:
            files = ["."]

        overwrite_all: Optional[bool] = None

        if PutArguments.YES_TO_ALL in args:
            overwrite_all = True
        if PutArguments.NO_TO_ALL in args:
            overwrite_all = False

        v("Overwrite all mode: %s", bool_to_str(overwrite_all))

        put_response = connection.put()

        # if not is_data_response(put_response):
        #     print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
        #     return

        if not is_success_response(put_response):
            Client._handle_connection_error_response(connection, put_response)
            return

        transaction_id = put_response["data"].get("transaction")
        port = put_response["data"].get("port")

        if not transaction_id or not port:
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        v("Successfully PUTed")
        transfer_socket = SocketTcpOut(
            connection.server_info.get("ip"), port,
            ssl_context=get_ssl_context(),
            ssl_server_side=False
        )

        files = sorted(files, reverse=True)
        sendfiles: List[dict] = []

        for f in files:
            _, trail = os.path.split(f)
            d("-> trail: %s", trail)
            sendfile = {
                "local": f,
                "remote": trail
            }
            d("Adding sendfile %s", json_to_pretty_str(sendfile))
            sendfiles.append(sendfile)


        def send_file(local_path: str, remote_path: str):
            nonlocal overwrite_all

            fstat = os.lstat(local_path)
            fsize = fstat.st_size

            if S_ISDIR(fstat.st_mode):
                ftype = FTYPE_DIR
            elif S_ISREG(fstat.st_mode):
                ftype = FTYPE_FILE
            else:
                w("Unknown file type")
                return

            finfo = {
                "name": remote_path,
                "ftype": ftype,
                "size": fsize
            }

            d("send_file finfo: %s", json_to_pretty_str(finfo))

            d("doing a put_next_info")

            resp = connection.put_next_info(transaction_id, finfo)

            if not is_success_response(resp):
                Client._handle_connection_error_response(connection, resp)
                return

            # Overwrite handling

            if is_data_response(resp) and resp.get("data") == "ask_overwrite":

                # Ask whether overwrite just once or forever
                current_overwrite_decision = overwrite_all

                # Ask until we get a valid answer
                while current_overwrite_decision is None:

                    overwrite_answer = input(
                        "{} already exists, overwrite it? [Y : yes / yy : yes to all / n : no / nn : no to all] "
                            .format(remote_path)
                    ).lower()

                    if not overwrite_answer or overwrite_answer == "y":
                        current_overwrite_decision = True
                    elif overwrite_answer == "n":
                        current_overwrite_decision = False
                    elif overwrite_answer == "yy":
                        current_overwrite_decision = overwrite_all = True
                    elif overwrite_answer == "nn":
                        current_overwrite_decision = overwrite_all = False
                    else:
                        w("Invalid answer, asking again")

                if current_overwrite_decision is False:
                    d("Skipping " + remote_path)
                    return
                else:
                    d("Will overwrite file")

            progressor = FileProgressor(
                fsize,
                description="PUT " + local_path,
                color_progress=PROGRESS_COLOR,
                color_done=DONE_COLOR
            )

            if ftype == FTYPE_DIR:
                d("Sent a DIR, nothing else to do")
                progressor.done()
                return

            d("Actually sending the file")

            BUFFER_SIZE = 4096

            f = open(local_path, "rb")

            cur_pos = 0

            while cur_pos < fsize:
                r = random.random() * 0.001
                time.sleep(0.001 + r)

                chunk = f.read(BUFFER_SIZE)
                d("Read chunk of %dB", len(chunk))

                if not chunk:
                    d("Finished %s", local_path)
                    # FIXME: sending something?
                    break

                transfer_socket.send(chunk)

                cur_pos += len(chunk)
                progressor.update(cur_pos)

            d("DONE %s", local_path)
            f.close()

            progressor.done()


        while sendfiles:
            v("Putting another file info")
            next_file = sendfiles.pop()

            # Check what is this
            # 1. Non existing: skip
            # 2. A file: send it directly (parent dirs won't be replicated)
            # 3. A dir: send it recursively

            next_file_local = next_file.get("local")
            next_file_remote = next_file.get("remote")

            if os.path.isfile(next_file_local):
                # Send it directly
                d("-> is a FILE")
                send_file(next_file_local, next_file_remote)

            elif os.path.isdir(next_file_local):
                # Send it recursively

                d("-> is a DIR")

                # Directory found
                dir_files = sorted(os.listdir(next_file_local), reverse=True)

                if dir_files:

                    v("Found a filled directory: adding all inner files to remaining_files")
                    for f in dir_files:
                        f_path_local = os.path.join(next_file_local, f)
                        f_path_remote = os.path.join(next_file_remote, f)
                        # Push to the begin instead of the end
                        # In this way we perform a breadth-first search
                        # instead of a depth-first search, which makes more sense
                        # because we will push the files that belongs to the same
                        # directory at the same time
                        sendfile = {
                            "local": f_path_local,
                            "remote": f_path_remote
                        }
                        d("Adding sendfile %s", json_to_pretty_str(sendfile))

                        sendfiles.append(sendfile)
                else:
                    v("Found an empty directory")
                    d("Pushing an info for the empty directory")

                    send_file(next_file_local, next_file_remote)
            else:
                eprint("Failed to send '{}'".format(next_file_local))
                w("Unknown file type, doing nothing")

    def _do_get(self,
                connection: Connection,
                files: List[str],
                args: Args):
        if not connection.is_connected():
            e("Connection must be opened for do GET")
            return

        get_response = connection.get(files)

        if not is_data_response(get_response):
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        if is_error_response(get_response):
            Client._handle_connection_error_response(connection, get_response)
            return

        transaction_id = get_response["data"].get("transaction")
        port = get_response["data"].get("port")

        if not transaction_id or not port:
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        v("Successfully GETed")

        transfer_socket = SocketTcpOut(
            connection.server_info.get("ip"), port,
            ssl_context=get_ssl_context(),
            ssl_server_side=False
        )

        overwrite_all: Optional[bool] = None

        if GetArguments.YES_TO_ALL in args:
            overwrite_all = True
        if GetArguments.NO_TO_ALL in args:
            overwrite_all = False

        v("Overwrite all mode: %s", bool_to_str(overwrite_all))

        while True:
            v("Fetching another file info")
            get_next_resp = connection.get_next_info(transaction_id)

            d("get_next_info()\n%s", get_next_resp)

            if not is_success_response(get_next_resp):
                print_error(ClientErrors.COMMAND_EXECUTION_FAILED)
                return

            next_file: FileInfo = get_next_resp.get("data")

            if not next_file:
                v("Nothing more to GET")
                break

            fname = next_file.get("name")
            fsize = next_file.get("size")
            ftype = next_file.get("ftype")

            d("NEXT: %s of type %s", fname, ftype)

            progressor = FileProgressor(
                fsize,
                description="GET " + fname,
                color_progress=PROGRESS_COLOR,
                color_done=DONE_COLOR
            )

            # Case: DIR
            if ftype == FTYPE_DIR:
                v("Creating dirs %s", fname)
                os.makedirs(fname, exist_ok=True)
                progressor.done()
                continue

            if ftype != FTYPE_FILE:
                w("Cannot handle this ftype")
                continue

            # Case: FILE
            parent_dirs, _ = os.path.split(fname)
            if parent_dirs:
                v("Creating parent dirs %s", parent_dirs)
                os.makedirs(parent_dirs, exist_ok=True)

            # Check wheter it already exists
            if os.path.isfile(fname):
                w("File already exists, asking whether overwrite it (if needed)")

                # Ask whether overwrite just once or forever
                current_overwrite_decision = overwrite_all

                # Ask until we get a valid answer
                while current_overwrite_decision is None:

                    overwrite_answer = input(
                        "{} already exists, overwrite it? [Y : yes / yy : yes to all / n : no / nn : no to all] "
                            .format(fname)
                    ).lower()

                    if not overwrite_answer or overwrite_answer == "y":
                        current_overwrite_decision = True
                    elif overwrite_answer == "n":
                        current_overwrite_decision = False
                    elif overwrite_answer == "yy":
                        current_overwrite_decision = overwrite_all = True
                    elif overwrite_answer == "nn":
                        current_overwrite_decision = overwrite_all = False
                    else:
                        w("Invalid answer, asking again")

                if current_overwrite_decision is False:
                    d("Skipping " + fname)
                    continue
                else:
                    d("Will overwrite file")

            v("Opening file '{}' locally".format(fname))
            file = open(fname, "wb")

            # Really get it

            BUFFER_SIZE = 4096

            read = 0

            while read < fsize:
                recv_size = min(BUFFER_SIZE, fsize - read)
                chunk = transfer_socket.recv(recv_size)

                if not chunk:
                    v("END")
                    break

                chunk_len = len(chunk)

                d("Read chunk of %dB", chunk_len)

                written_chunk_len = file.write(chunk)

                if chunk_len != written_chunk_len:
                    w("Written less bytes than expected: something will go wrong")
                    exit(-1)

                read += written_chunk_len
                d("%d/%d (%.2f%%)", read, fsize, read / fsize * 100)
                progressor.update(read)

            progressor.done()
            d("DONE %s", fname)
            file.close()

            if os.path.getsize(fname) == fsize:
                d("File OK (length match)")
            else:
                e("File length mismatch. %d != %d",
                  os.path.getsize(fname), fsize)

        v("GET transaction %s finished, closing socket", transaction_id)
        transfer_socket.close()

    def get(self, args: Args):
        # 'get' command is multipurpose
        # 1. Inside a connection: get a list of files (or directories)
        # 2. Outside a connection:
        #   2.1 get a file sharing (ftype = 'file')
        #   2.2 get all the content of directory sharing (ftype = 'dir')

        if self.is_connected():
            d("GET => get_files")
            self.get_files(args)
        else:
            d("GET => get_sharing")
            self.get_sharing(args)

    def put(self, args: Args):
        if self.is_connected():
            d("PUT => put_files")
            self.put_files(args)
        else:
            d("PUT => put_sharing")
            self.put_sharing(args)

    def _discover_server(self, location: str) -> Optional[ServerInfo]:

        if not location:
            e("Server location must be specified")
            return None

        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))

            # Check if 'location' matches (if specified)
            if location == a_server_info.get("name") or \
                location == a_server_info.get("ip") or \
                location == "{}:{}".format(a_server_info.get("ip"),
                                           a_server_info.get("port")):
                server_info = a_server_info
                return False    # Stop DISCOVER

            return True  # Continue DISCOVER

        Discoverer(self._server_discover_port, response_handler).discover()
        return server_info


    def _discover_sharing(self,
                          name: str = None,
                          location: str = None,
                          ftype: FileType = None,
                          timeout: int = Discoverer.DEFAULT_TIMEOUT) -> Tuple[Optional[SharingInfo], Optional[ServerInfo]]:
        """
        Performs a discovery for find whose server the sharing with the given
        'name' belongs to.

        """

        sharing_info: Optional[SharingInfo] = None
        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:

            nonlocal sharing_info
            nonlocal server_info

            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))

            # Check if 'location' matches (if specified)
            if location and \
                    location != a_server_info.get("name") and \
                    location != a_server_info.get("ip") and \
                    location != "{}:{}".format(a_server_info.get("ip"),
                                               a_server_info.get("port")):
                d("Discarding server info which does not match the location filter '%s'", location)
                return True  # Continue DISCOVER

            for a_sharing_info in a_server_info.get("sharings"):

                # Check if 'name' matches (if specified)
                if name and a_sharing_info.get("name") != name:
                    d("Ignoring sharing which does not match the name filter '%s'", name)
                    continue

                if ftype and a_sharing_info.get("ftype") != ftype:
                    d("Ignoring sharing which does not match the ftype filter '%s'", ftype)
                    w("Found a sharing with the right name but wrong ftype, wrong command maybe?")
                    continue

                # FOUND
                d("Sharing [%s] found at %s:%d",
                  a_sharing_info.get("name"),
                  a_server_info.get("ip"),
                  a_server_info.get("port"),
              )

                server_info = a_server_info
                sharing_info = a_sharing_info
                return False    # Stop DISCOVER

            return True             # Continue DISCOVER

        Discoverer(self._server_discover_port, response_handler).discover(timeout)
        return sharing_info, server_info


    @staticmethod
    def _sharings_string(sharings: List[SharingInfo], details: bool = False) -> str:
        s = ""

        d_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_DIR]
        f_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_FILE]

        def sharing_string(sharing: SharingInfo):
            ss = "  - " + sharing.get("name")

            if details:
                details_list = []
                if sharing.get("auth"):
                    details_list.append("auth required")
                if sharing.get("read_only"):
                    details_list.append("read only")
                if details_list:
                    ss += "  ({})".format(", ".join(details_list))
            ss += "\n"
            return ss

        if d_sharings:
            s += "  DIRECTORIES\n"
            for dsh in d_sharings:
                s += sharing_string(dsh)

        if f_sharings:
            s += "  FILES\n"
            for fsh in f_sharings:
                s += sharing_string(fsh)

        return s.rstrip("\n")

    @staticmethod
    def _print_tree_files_info(root: TreeNodeDict,
                               max_depth: int = None,
                               show_size: bool = False):
        for prefix, node, depth in TreeRenderPostOrder(root, depth=max_depth):
            ftype = node.get("ftype")
            size = node.get("size")

            print("{}{}{}".format(
                prefix,
                "[{}]  ".format(size_str(size).rjust(4)) if show_size else "",
                fg(node.get("name"), color=DIR_COLOR if ftype == FTYPE_DIR else FILE_COLOR),
            ))


    @staticmethod
    def _print_list_files_info(infos: List[FileInfo],
                               show_file_type: bool = False,
                               show_size: bool = False,
                               show_hidden: bool = False,
                               compact: bool = True,
                               ):
        sstrings: List[StyledString] = []

        for info in infos:
            d("f_info: %s", info)

            fname = info.get("name")

            if not show_hidden and is_hidden(fname):
                d("Not showing hidden files: %s", fname)
                continue

            size = info.get("size")

            if info.get("ftype") == FTYPE_DIR:
                ftype_short = "D"
                fname_styled = fg(fname, DIR_COLOR)
            else:
                ftype_short = "F"
                fname_styled = fg(fname, FILE_COLOR)

            file_str = ""

            if show_file_type:
                s = ftype_short + "  "
                # if not compact:
                #     s = s.ljust(3)
                file_str += s

            if show_size:
                s = size_str(size).rjust(4) + "  "
                file_str += s

            file_str_styled = file_str

            file_str += fname
            file_str_styled += fname_styled

            sstrings.append(StyledString(file_str, file_str_styled))

        if not compact:
            for ss in sstrings:
                print(ss.styled_string)
        else:
            print_tabulated(sstrings)

    def _handle_error_response(self, resp: Response):
        Client._handle_connection_error_response(self.connection, resp)

    @staticmethod
    def _handle_connection_error_response(connection: Connection, resp: Response):
        if is_error_response(ServerErrors.NOT_CONNECTED):
            v("Received a NOT_CONNECTED response: destroying connection")
            connection.close()
        print_response_error(resp)


# ========================


class Shell:

    def __init__(self, client: Client):
        self.prompt = None
        self.line_buffer = None

        self.client = client

        self._suggestions_intent: Optional[SuggestionsIntent] = None

        self._shell_command_dispatcher: Dict[str, Callable[[Args], None]] = {
            Commands.HELP: self._help,
            Commands.EXIT: self._exit,
        }

        readline.parse_and_bind("tab: complete")
        # readline.parse_and_bind("set output-meta on")
        # readline.parse_and_bind("set vi-cmd-mode-string none")
        # readline.parse_and_bind("set visible-stats on")
        # readline.parse_and_bind("set colored-stats on")
        # readline.parse_and_bind("set mark-directories on")
        readline.parse_and_bind("set completion-query-items 40")

        # Remove '-' from the delimiters for handle suggestions
        # starting with '-' properly
        # `~!@#$%^&*()-=+[{]}\|;:'",<>/?
        readline.set_completer_delims(readline.get_completer_delims()
                                      .replace("-", "")
                                      # .replace(os.path.sep, "")
                                      )

        readline.set_completion_display_matches_hook(self.display_suggestions)

        readline.set_completer(self.next_suggestion)

    def display_suggestions(self, substitution, matches, longest_match_length):
        # Simulate the default behaviour of readline, but:
        # 1. Separate the concept of suggestion/rendered suggestion: in this
        #    way we can render a colored suggestion while using the readline
        #    core for treat it as a simple screent
        # 2. Internally handles the max_columns constraints
        print("")
        print_tabulated(self._suggestions_intent.suggestions,
                        max_columns=self._suggestions_intent.max_columns)
        print(self.prompt + self.line_buffer, end="", flush=True)

    def next_suggestion(self, token: str, count: int):
        self.line_buffer = readline.get_line_buffer()
        # d("[%d] next_suggestion\n text = %s\n line_buffer = %s", state, text, raw_line_buffer)
        # d("get_completer_delims %s", readline.get_completer_delims())
        # d("get_completion_type %d", readline.get_completion_type())

        line_buffer = self.line_buffer.lstrip()

        if count == 0:
            self._suggestions_intent = SuggestionsIntent([])
            # self._suggestions
            # columns_count = -1
            # enable_completion = True
            # space_after_completion = True

            for comm_name, comm_info in COMMANDS_INFO.items():
                if line_buffer.startswith(comm_name + " "):
                    # Typing a COMPLETE command
                    # e.g. 'ls '

                    d("Fetching suggestions intent for command '%s'", comm_name)
                    self._suggestions_intent = comm_info.suggestions(token, line_buffer, self.client)
                    d("Fetched intent")
                    #
                    # if suggestions_intent:
                    #     self._suggestions = suggestions_intent.suggestions
                    #     columns_count = suggestions_intent.columns
                    #     enable_completion = suggestions_intent.completion
                    #     space_after_completion = suggestions_intent.space_after_completion

                    break

                if comm_name.startswith(line_buffer):
                    # Typing an INCOMPLETE command
                    # e.g. 'clos '

                    # Case 1: complete command
                    self._suggestions_intent.suggestions.append(StyledString(comm_name))

            # If there is only a command that begins with
            # this name, complete the command (and eventually insert a space)
            if self._suggestions_intent.completion and \
                    self._suggestions_intent.space_after_completion and \
                    len(self._suggestions_intent.suggestions) == 1:

                if is_bool(self._suggestions_intent.space_after_completion):
                    append_space = self._suggestions_intent.space_after_completion
                else:
                    append_space = self._suggestions_intent.space_after_completion(
                        self._suggestions_intent.suggestions[0]
                    )

                if append_space:
                    self._suggestions_intent.suggestions[0].string += " "

            # d("Configuring readline with cols = %d, autocomplete = %d",
            #   columns_count, enable_completion)
            #
            # readline.parse_and_bind("set completion-display-width {}".format(
            #     columns_count
            # ))
            # readline.parse_and_bind("tab: {}".format(
            #     "complete" if enable_completion else "possible-completions"
            # ))

            self._suggestions_intent.suggestions = \
                sorted(self._suggestions_intent.suggestions, key=lambda sugg: sugg.string.lower())

        if count < len(self._suggestions_intent.suggestions):
            d("Returning suggestion %d", count)
            return self._suggestions_intent.suggestions[count].string

        return None

    def input_loop(self):
        command = None
        while command != Commands.EXIT:
            try:
                self.prompt = self._build_prompt_string()
                command_line = input(self.prompt)

                if not command_line:
                    w("Empty command line")
                    continue

                try:
                    command_line_parts = shlex.split(command_line)
                except ValueError:
                    w("Invalid command line")
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                if len(command_line_parts) < 1:
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                command = command_line_parts[0]
                command_args = Args(command_line_parts[1:])

                outcome = \
                    self._execute_shell_command(command, command_args) or \
                    self.client.execute_command(command, command_args)

                if not outcome:
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
            except PyroError as pyroerr:
                v("Pyro error occurred %s", pyroerr)
                print_error(ClientErrors.CONNECTION_ERROR)
                # Close client connection anyway
                try:
                    if self.client.is_connected():
                        d("Trying to close connection gracefully")
                        self.client.close()
                except PyroError:
                    d("Cannot communicate with remote: invalidating connection")
                    self.client.connection = None
            except KeyboardInterrupt:
                v("CTRL+C detected")
                print()
            except EOFError:
                v("CTRL+D detected: exiting")
                if self.client.is_connected():
                    self.client.close()
                break

    def _build_prompt_string(self):
        if self.client.is_connected():
            prompt_base = "{}:/{}  ##  ".format(
                self.client.connection.sharing_name(),
                self.client.connection.rpwd()
            )
        else:
            prompt_base = ""

        return prompt_base + os.getcwd() + "> "

    def _execute_shell_command(self, command: str, args: Args) -> bool:
        if command not in self._shell_command_dispatcher:
            return False

        d("Handling shell command %s (%s)", command, args)
        self._shell_command_dispatcher[command](args)
        return True

    def _help(self, _: Args):
        print(HELP_COMMANDS)

    def _exit(self, _: Args):
        pass


def main():
    args = Args(sys.argv[1:])

    init_colors(ClientArguments.NO_COLOR not in args)

    verbosity = 0
    tracing = 0

    if ClientArguments.VERBOSE in args:
        verbosity = to_int(args.get_param(ClientArguments.VERBOSE, default=VERBOSITY_VERBOSE))
        if verbosity is None:
            abort("Invalid --verbose parameter value")

    if ClientArguments.TRACE in args:
        tracing = to_int(args.get_param(ClientArguments.TRACE, default=1))
        if tracing is None:
            abort("Invalid --trace parameter value")

    init_logging(verbosity)
    init_tracing(True if tracing else False)

    i(APP_INFO)
    d(args)

    if ClientArguments.HELP in args:
        terminate(HELP_APP)

    if ClientArguments.VERSION in args:
        terminate(APP_INFO)


    server_discover_port = DEFAULT_DISCOVER_PORT

    if ClientArguments.PORT in args:
        server_discover_port = to_int(args.get_param(ClientArguments.PORT))

    # Start in interactive mode
    client = Client(server_discover_port)

    # Allow some commands directly from command line
    # GET, SCAN
    cli_command_line = args.get_params()

    start_shell = True if not cli_command_line else False

    if not start_shell:
        command = cli_command_line.pop(0)

        if command not in CLI_COMMANDS:
            abort("Unknown command: {}".format(command))

        start_shell = (command == Commands.OPEN)

        # Execute directly
        # Take out the first token as "command" and leave
        # everything else as it is
        d("Executing command directly from command line: %s (%s)", command, args)
        client.execute_command(command, args)

    # Start the shell
    # 1. If a command was not specified
    # 2. We are connected (due to open from a direct command)
    if start_shell:
        # Start the shell
        v("Executing shell")
        shell = Shell(client)
        shell.input_loop()


if __name__ == "__main__":
    main()
