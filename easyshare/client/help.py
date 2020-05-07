import os
from abc import abstractmethod, ABC
from typing import List, Callable, Union, Optional, Dict, Type

from easyshare.client.commands import Commands
from easyshare.client.ui import StyledString
from easyshare.client.client import Client
from easyshare.logging import get_logger
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_DIR, FTYPE_FILE
from easyshare.protocol.response import is_data_response
from easyshare.shared.common import DIR_COLOR, FILE_COLOR
from easyshare.utils.colors import fg
from easyshare.utils.os import ls
from easyshare.utils.str import rightof

log = get_logger(__name__)


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


class CommandArgInfo:
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
    def args(cls) -> List[CommandArgInfo]:
        return []

    @classmethod
    def suggestions(cls, token: str, line: str, client: Client) -> Optional[SuggestionsIntent]:
        return None


class CommandArgsInfo(CommandInfo):

    @classmethod
    def args(cls) -> List[CommandArgInfo]:
        if not hasattr(cls, "ARGS"):
            # Retrieve the CommandArgInfo of this class
            ARGS = []

            for attrname in dir(cls):
                if attrname.startswith("_"):
                    continue
                command_arg_info = getattr(cls, attrname)
                if isinstance(command_arg_info, CommandArgInfo):
                    ARGS.append(command_arg_info)

            setattr(cls, "ARGS", ARGS)
        return getattr(cls, "ARGS")

    @classmethod
    def suggestions(cls, token: str, line: str, client: 'Client') -> Optional[SuggestionsIntent]:
        log.i("Token: %s", token)
        if not token.startswith("-"):
            # This class handles only the kwargs ('-', '--')
            # The sub classes can provide something else
            return None

        classargs = cls.args()

        log.d("Computing (%d) args suggestions for", len(classargs))

        longest_args_names = 0

        for comm_args in classargs:
            longest_args_names = max(
                longest_args_names,
                len(comm_args.args_str())
            )

        suggestions = [StyledString(comm_args.args_help_str(justify=longest_args_names))
                       for comm_args in classargs]

        return SuggestionsIntent(suggestions,
                                 completion=False,
                                 max_columns=1)


class ListCommandArgsInfo(CommandArgsInfo, ABC):
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


class ListLocalCommandInfo(ListCommandArgsInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client: 'Client') -> List[FileInfo]:
        log.i("List on token = '%s', line = '%s'", token, line)
        pattern = rightof(line, " ", from_end=True)
        path_dir, path_trail = os.path.split(os.path.join(os.getcwd(), pattern))
        log.i("ls-ing on %s", path_dir)
        return ls(path_dir)


class ListRemoteCommandInfo(ListCommandArgsInfo, ABC):
    @classmethod
    def list(cls, token: str, line: str, client: 'Client') -> List[FileInfo]:
        if not client or not client.is_connected_to_sharing():
            log.w("Cannot list suggestions on a non connected client")
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


class ListAllFilter(ListCommandArgsInfo, ABC):
    @classmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        return True


class ListDirsFilter(ListCommandArgsInfo, ABC):
    @classmethod
    def display_path_filter(cls, finfo: FileInfo) -> bool:
        return finfo.get("ftype") == FTYPE_DIR


class ListFilesFilter(ListCommandArgsInfo, ABC):
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
    V0 = CommandArgInfo(["0"], "error")
    V1 = CommandArgInfo(["1"], "error / warning")
    V2 = CommandArgInfo(["2"], "error / warning / info")
    V3 = CommandArgInfo(["3"], "error / warning / info / verbose")
    V4 = CommandArgInfo(["4"], "error / warning / info / verbose / debug")

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
    T0 = CommandArgInfo(["0"], "enable packet tracing")
    T1 = CommandArgInfo(["1"], "disable packet tracing")

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


class BaseLsCommandInfo(CommandArgsInfo):
    SORT_BY_SIZE = CommandArgInfo(["-s", "--sort-size"], "Sort by size")
    REVERSE = CommandArgInfo(["-r", "--reverse"], "Reverse sort order")
    GROUP = CommandArgInfo(["-g", "--group"], "Group by file type")
    SIZE = CommandArgInfo(["-S"], "Show file size")
    DETAILS = CommandArgInfo(["-l"], "Show all the details")


class LsCommandInfo(BaseLsCommandInfo, ListLocalAllCommandInfo):
    pass


class LsEnhancedCommandInfo(ListLocalAllCommandInfo):
    pass


class RlsCommandInfo(BaseLsCommandInfo, ListRemoteAllCommandInfo):
    pass


class BaseTreeCommandInfo(CommandArgsInfo):
    SORT_BY_SIZE = CommandArgInfo(["-s", "--sort-size"], "Sort by size")
    REVERSE = CommandArgInfo(["-r", "--reverse"], "Reverse sort order")
    GROUP = CommandArgInfo(["-g", "--group"], "Group by file type")
    MAX_DEPTH = CommandArgInfo(["-d", "--depth"], "Maximum depth")
    SIZE = CommandArgInfo(["-S"], "Show file size")
    DETAILS = CommandArgInfo(["-l"], "Show all the details")


class TreeCommandInfo(BaseTreeCommandInfo, ListLocalAllCommandInfo):
    pass


class RtreeCommandInfo(BaseTreeCommandInfo, ListRemoteAllCommandInfo):
    pass


class GetCommandInfo(ListRemoteAllCommandInfo):
    YES_TO_ALL = CommandArgInfo(["-Y", "--yes"], "Always overwrite existing files")
    NO_TO_ALL = CommandArgInfo(["-N", "--no"], "Never overwrite existing files")


class PutCommandInfo(ListLocalAllCommandInfo):
    YES_TO_ALL = CommandArgInfo(["-Y", "--yes"], "Always overwrite existing files")
    NO_TO_ALL = CommandArgInfo(["-N", "--no"], "Never overwrite existing files")


class ScanCommandInfo(CommandArgsInfo):
    DETAILS = CommandArgInfo(["-l"], "Show all the details")


COMMANDS_INFO: Dict[str, Type[CommandInfo]] = {
    Commands.HELP: CommandInfo,
    Commands.EXIT: CommandInfo,

    Commands.TRACE: TraceCommandInfo,
    Commands.TRACE_SHORT: TraceCommandInfo,

    Commands.VERBOSE: VerboseCommandInfo,
    Commands.VERBOSE_SHORT: VerboseCommandInfo,


    Commands.LOCAL_CURRENT_DIRECTORY: CommandInfo,
    Commands.LOCAL_LIST_DIRECTORY: LsCommandInfo,
    Commands.LOCAL_LIST_DIRECTORY_ENHANCED: LsEnhancedCommandInfo,
    Commands.LOCAL_TREE_DIRECTORY: TreeCommandInfo,
    Commands.LOCAL_CHANGE_DIRECTORY: ListLocalDirsCommandInfo,
    Commands.LOCAL_CREATE_DIRECTORY: ListLocalDirsCommandInfo,
    Commands.LOCAL_COPY: ListLocalAllCommandInfo,
    Commands.LOCAL_MOVE: ListLocalAllCommandInfo,
    Commands.LOCAL_REMOVE: ListLocalAllCommandInfo,
    Commands.LOCAL_EXEC: ListLocalAllCommandInfo,
    Commands.LOCAL_EXEC_SHORT: ListLocalAllCommandInfo,


    Commands.REMOTE_CURRENT_DIRECTORY: CommandInfo,
    Commands.REMOTE_LIST_DIRECTORY: RlsCommandInfo,
    Commands.REMOTE_TREE_DIRECTORY: RtreeCommandInfo,
    Commands.REMOTE_CHANGE_DIRECTORY: ListRemoteDirsCommandInfo,
    Commands.REMOTE_CREATE_DIRECTORY: ListRemoteDirsCommandInfo,
    Commands.REMOTE_COPY: ListRemoteAllCommandInfo,
    Commands.REMOTE_MOVE: ListRemoteAllCommandInfo,
    Commands.REMOTE_REMOVE: ListRemoteAllCommandInfo,
    Commands.REMOTE_EXEC: CommandInfo,
    Commands.REMOTE_EXEC_SHORT: CommandInfo,


    Commands.SCAN: ScanCommandInfo,
    Commands.OPEN: CommandInfo,
    Commands.CLOSE: CommandInfo,

    Commands.GET: GetCommandInfo,
    Commands.PUT: PutCommandInfo,

    Commands.INFO: CommandInfo,
    Commands.PING: CommandInfo,
}
