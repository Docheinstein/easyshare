import os
import re
from abc import abstractmethod, ABC
from typing import List, Callable, Union, Optional, Dict, Type

from easyshare.args import Option, PRESENCE_PARAM, INT_PARAM, NoPosArgsSpec, PosArgsSpec, VarArgsSpec, STR_PARAM, \
    StopParseArgsSpec, KeepQuotesArgsSpec, OptIntPosArgSpec, KeyValArgsSpec
from easyshare.commands import CommandHelp, CommandOptionInfo
from easyshare.es.ui import StyledString
from easyshare.logging import get_logger
from easyshare.common import DIR_COLOR, FILE_COLOR
from easyshare.protocol.responses import is_data_response
from easyshare.protocol.types import FTYPE_FILE, FTYPE_DIR, FileInfo
from easyshare.settings import Settings
from easyshare.styling import fg
from easyshare.utils.obj import values
from easyshare.utils.os import ls
from easyshare.utils.path import LocalPath

log = get_logger(__name__)


# Contains only helps and meta information
# of the commands, not the real implementation

# =============================================
# =============== COMMANDS ====================
# =============================================

class Commands:
    """ es commands """
    HELP = "help"

    EXIT = "exit"
    QUIT = "quit"

    TRACE = "trace"
    VERBOSE = "verbose"

    ALIAS = "alias"
    SET = "set"

    LOCAL_CURRENT_DIRECTORY = "pwd"
    LOCAL_LIST_DIRECTORY = "ls"
    LOCAL_LIST_DIRECTORY_ENHANCED = "l"
    LOCAL_TREE_DIRECTORY = "tree"
    LOCAL_FIND = "find"
    LOCAL_DISK_USAGE = "du"
    LOCAL_CHANGE_DIRECTORY = "cd"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_COPY = "cp"
    LOCAL_MOVE = "mv"
    LOCAL_REMOVE = "rm"
    LOCAL_SHELL = "shell"

    REMOTE_CURRENT_DIRECTORY = "rpwd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_LIST_DIRECTORY_ENHANCED = "rl"
    REMOTE_TREE_DIRECTORY = "rtree"
    REMOTE_FIND = "rfind"
    REMOTE_DISK_USAGE = "rdu"
    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_COPY = "rcp"
    REMOTE_MOVE = "rmv"
    REMOTE_REMOVE = "rrm"
    REMOTE_SHELL = "rshell"

    SCAN = "scan"

    CONNECT = "connect"
    DISCONNECT = "disconnect"

    OPEN = "open"
    CLOSE = "close"

    GET = "get"
    PUT = "put"

    LIST = "list"
    INFO = "info"
    PING = "ping"

COMMANDS = values(Commands)


# ==================================================
# ============ BASE COMMAND INFO ===================
# ==================================================

class SuggestionsIntent:
    """
    Bundle provided by a command: contains the suggestions
    (e.g. files of the current directory) and other render specifications.
    """
    def __init__(self,
                 suggestions: List[StyledString],
                 *,
                 completion: bool = True,
                 insert_after_completion: Union[Callable[[str], str], str] = " ",
                 max_columns: int = None,
                 ):
        self.suggestions: List[StyledString] = suggestions
        self.completion: bool = completion
        self.insert_after_completion: Union[Callable[[str], str], str] = insert_after_completion
        self.max_columns: int = max_columns

    def __str__(self):
        return "".join([str(s) for s in self.suggestions])



class CommandInfo(CommandHelp, ABC):
    """ Provide full information of a command and the suggestions too """
    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
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
            [len(o.aliases_str()) + len(" ") + len(o.params_str()) for o in options]
        )

        log.d("longest_option string length: %d", longest_option_length)

        suggestions = []

        # TODO param

        for opt in options:
            suggestions.append(StyledString(
                opt.to_str(justification=longest_option_length + 6)
            ))

        return SuggestionsIntent(suggestions,
                                 completion=False,
                                 max_columns=1)



class FilesSuggestionsCommandInfo(CommandInfo):
    """ Base suggestions provided of list of files/directory """
    @classmethod
    @abstractmethod
    def _file_info_filter(cls, finfo: FileInfo) -> bool:
        """ The subclass should say whether the given file info should be displayed """
        pass

    @classmethod
    @abstractmethod
    def _provide_file_info_list(cls, token: str, client) -> List[FileInfo]:
        """ The file list to suggest, after being filtered by '_file_info_filter' """
        pass

    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        log.d("Providing files listing suggestions")

        suggestions_intent = super().suggestions(token, client)
        if suggestions_intent:
            return suggestions_intent

        suggestions = []
        for finfo in cls._provide_file_info_list(token, client):
            log.d("Suggestion finfo: %s", finfo)

            fname = finfo.get("name")

            if not cls._file_info_filter(finfo):
                log.d("%s doesn't pass the filter", fname)
                continue

            _, fname_tail = os.path.split(fname)
            token_head, token_tail = os.path.split(token)

            fname_tail_lower = fname_tail.lower()
            token_tail_lower = token_tail.lower()
            if not fname_tail_lower.startswith(token_tail_lower):
                log.d(f"    (NO match: '{fname_tail_lower}' not starts with '{token_tail_lower}')")
                continue

            log.d(f"    (OK match: '{fname_tail_lower}' starts with '{token_tail_lower}')")

            model = os.path.join(token_head, fname_tail)
            view = fname_tail

            if finfo.get("ftype") == FTYPE_DIR:
                # Append a dir, with a trailing / so that the next
                # suggestion can continue to traverse the file system
                suggestions.append(StyledString(model + "/", fg(view + "/", color=DIR_COLOR)))
            else:
                # Append a file, with a trailing space since there
                # is no need to traverse the file system
                suggestions.append(StyledString(model, fg(view, color=FILE_COLOR)))

        log.d(f"There will be {len(suggestions)} suggestions")
        return SuggestionsIntent(suggestions,
                                 completion=True,
                                 insert_after_completion=lambda s: " " if not s.endswith("/") else "")


# ==================================================
# =========== FINDINGS SUGGESTIONS =================
# ==================================================

FINDING_RE = re.compile(r"\$([a-zA-Z])?(\d+)?")

class FilesAndFindingsSuggestionsCommandInfo(FilesSuggestionsCommandInfo, ABC):
    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        findings = cls._provide_findings_list(token, client)
        if findings:
            log.d(f"There will be {len(findings)} findings suggestions")
            return SuggestionsIntent([StyledString(finding) for finding in findings],
                                     completion=True)

        # No findings, use default suggestions provider
        return super().suggestions(token, client)

    @classmethod
    def _provide_findings_list(cls, token: str, client) -> List[str]:
        match = re.match(FINDING_RE, token)
        if match:
            log.d("Handling valid finding token")

            letter_filter = match.groups()[0]
            n_filter = match.groups()[1]

            log.d(f"letter_filter {letter_filter}")
            log.d(f"n_filter {n_filter}")

            findings = []
            all_findings = cls._provide_findings_dict(token, client)
            # log.d(f"Checking against {all_findings}")

            for (letter, findings_for_letter) in all_findings.items():
                log.d(f"Checking against letter={letter}")

                # Letter filter?
                if letter_filter and letter != letter_filter:
                    continue

                # N filter?
                for i, finding in enumerate(findings_for_letter.infos):
                    idx = i +1
                    log.d(f"Checking against {letter}{idx}")
                    if n_filter and not str(idx).startswith(n_filter):
                        continue

                    # All filters passed, valid suggestion
                    log.d(f"Finding: ${letter}{idx}")
                    findings.append(f"${letter}{idx}")

            return findings
        return []


    @classmethod
    @abstractmethod
    def _provide_findings_dict(cls, token, client) -> Dict[str, 'Findings']:
        pass

# ==================================================
# =========== LOCAL/REMOTE FILES SUGGESTIONS =======
# ==================================================


class LocalFilesSuggestionsCommandInfo(FilesAndFindingsSuggestionsCommandInfo, ABC):
    """ Files suggestions provider of local files """
    @classmethod
    def _provide_file_info_list(cls, token: str, client) -> List[FileInfo]:
        log.d("List on token = '%s'", token)
        # token contains only the last part after a /
        # e.g. /tmp/something => something
        # we have to use all the path (line)

        # Take the part after the last space

        # Take the parent
        # path.parent can't be used unconditionally since it returns
        # the parent dir even if "pattern" ends with a os.path.sep

        # The only (known) strange case occurs in the following case
        # ls LocalPath(/home/user/.) -> /home/user while i want it to
        # be /home/user/. literally, for suggests .vimrc, ...

        _, trail = os.path.split(token)
        listing_hidden_file = trail.startswith(".")

        path = LocalPath(token)
        log.d(f"=> path = {path}")

        if not token.endswith(os.path.sep) and trail != os.path.sep:
            path = path.parent

        log.i("ls-ing for suggestions on '%s'", path)
        return ls(path, details=False, hidden=listing_hidden_file)

    @classmethod
    def _provide_findings_dict(cls, token, client) -> Dict[str, 'Findings']:
        log.d("_provide_findings_dict: _local_findings")
        return client._local_findings


class RemoteFilesSuggestionsCommandInfo(FilesAndFindingsSuggestionsCommandInfo, ABC):
    """ Files suggestions provider of remote files (performs an rls) """

    @classmethod
    def _provide_file_info_list(cls, token: str, client) -> List[FileInfo]:
        if not client or not client.is_connected_to_sharing():
            log.w("Cannot list suggestions on a non connected es")
            return []

        log.i("List remotely on token = '%s'", token)
        path_dir, path_trail = os.path.split(token)
        listing_hidden_file = path_trail.startswith(".")

        log.i("rls-ing on %s", token)

        resp = client.connection.rls(sort_by=["name"], hidden=listing_hidden_file,
                                     path=path_dir)

        if not is_data_response(resp):
            log.w("Unable to retrieve a valid response for rls")
            return []

        return resp.get("data")

    @classmethod
    def _provide_findings_dict(cls, token, client) -> Dict[str, 'Findings']:
        log.d("_provide_findings_dict: _remote_findings")
        return client._remote_findings

# ==================================================
# ================ FILE INFO FILTERS ===============
# ==================================================


class AllFilesFilter(FilesSuggestionsCommandInfo, ABC):
    """ Suggestions provider that doesn't filter the file list """
    @classmethod
    def _file_info_filter(cls, finfo: FileInfo) -> bool:
        return True # show files and directories


class DirsOnlyFilter(FilesSuggestionsCommandInfo, ABC):
    """ Suggestions provider that keeps only the directories """
    @classmethod
    def _file_info_filter(cls, finfo: FileInfo) -> bool:
        return finfo.get("ftype") == FTYPE_DIR


class FilesOnlyFilter(FilesSuggestionsCommandInfo, ABC):
    """ Suggestions provider that keeps only the files """
    @classmethod
    def _file_info_filter(cls, finfo: FileInfo) -> bool:
        return finfo.get("ftype") == FTYPE_FILE


# ==================================================
# ==== REAL IMPL LOCAL/REMOTE FILES SUGGESTIONS ====
# ==================================================


class LocalAllFilesSuggestionsCommandInfo(LocalFilesSuggestionsCommandInfo, AllFilesFilter, ABC):
    pass


class LocalDirsOnlySuggestionsCommandInfo(LocalFilesSuggestionsCommandInfo, DirsOnlyFilter, ABC):
    pass


class LocalFilesOnlySuggestionsCommandInfo(LocalFilesSuggestionsCommandInfo, FilesOnlyFilter, ABC):
    pass


class RemoteAllFilesSuggestionsCommandInfo(RemoteFilesSuggestionsCommandInfo, AllFilesFilter, ABC):
    pass


class RemoteDirsOnlySuggestionsCommandInfo(RemoteFilesSuggestionsCommandInfo, DirsOnlyFilter, ABC):
    pass


class RemoteFilesOnlySuggestionsCommandInfo(RemoteFilesSuggestionsCommandInfo, FilesOnlyFilter, ABC):
    pass


# ==================================================
# ============== COMMON DESCRIPTIONS ===============
# ==================================================

class CommandInfoSynopsisEnhancer(CommandInfo, ABC):
    @classmethod
    @abstractmethod
    def _synopsis(cls):
        pass

class FastSharingConnectionCommandInfo(CommandInfoSynopsisEnhancer, ABC):
    @classmethod
    def synopsis(cls):
        return f"""\
{cls._synopsis()}

*SHARING_LOCATION* must be specified if and only if not already connected to \
a remote server. In that case the connection will be established before \
execute the command, as "**connect** *SHARING_LOCATION*" would do.

Type "**help** **connect**" for more information about *SHARING_LOCATION* format."""

class FastServerConnectionCommandInfo(CommandInfoSynopsisEnhancer, ABC):
    @classmethod
    def synopsis(cls):
        return f"""\
{cls._synopsis()}

*SERVER_LOCATION* must be specified if and only if not already connected to \
a remote server. In that case the connection will be established before \
execute the command, as "**connect** *SERVER_LOCATION*" would do.

Type "**help** **connect**" for more information about *SERVER_LOCATION* format."""


# ==================================================
# ========== REAL COMMANDS INFO IMPL ===============
# ==================================================

# ============ HELP ================

class Help(CommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "help"

    @classmethod
    def short_description(cls):
        return "show the help of a command"

    @classmethod
    def synopsis(cls):
        return """\
**help** [*COMMAND_OR_ALIAS*]\
"""

    @classmethod
    def long_description(cls):
        comms = "\n".join(["    " + comm for comm in sorted(COMMANDS_INFO.keys())])
        return f"""\
Show the help of *COMMAND_OR_ALIAS* if specified, or show the list of commands if no *COMMAND* is given.

*COMMAND_OR_ALIAS* can either be a default command or a custom alias (read from .esrc).

Available commands are:
{comms}"""

    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        log.d("Providing commands suggestions")

        suggestions = [StyledString(comm)
                       for comm in COMMANDS_INFO.keys() if comm.startswith(token)]

        return SuggestionsIntent(suggestions,
                                 completion=True,
                                 insert_after_completion=lambda s: " " if not s.endswith("/") else "")


# ============ EXIT ================

class Exit(CommandInfo, NoPosArgsSpec):
    @classmethod
    def name(cls):
        return "exit"

    @classmethod
    def short_description(cls):
        return "exit from the interactive shell"

    @classmethod
    def synopsis(cls):
        return """\
**exit**
**quit**\
"""

    @classmethod
    def long_description(cls):
        return f"""\
Exit from the interactive shell.

Open connections are automatically closed."""

# ============ TRACE ================

class Trace(CommandInfo, OptIntPosArgSpec):

    T0 = (["0"], "disabled")
    T1 = (["1"], "text/json")
    T2 = (["2"], "binary")

    @classmethod
    def name(cls):
        return "trace"

    @classmethod
    def short_description(cls):
        return "enable/disable packet tracing"

    @classmethod
    def synopsis(cls):
        return """\
**trace** [*LEVEL*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Change the tracing level to *LEVEL* (default is *0*, which is disabled).
When tracing is enabled, packets sent and received to and from the \
server for any operation are shown.

The allowed values of *LEVEL* are:
.A        .
*0*         disabled (default)
*1*         text
*2*         binary payloads
*3*         binary all (payload + header)
./A

If no argument is given, increase the tracing level or resets it to 0 \
if it exceeds the maximum."""


    @classmethod
    def examples(cls):
        return """\
Usage example:

**/home/stefano>** scan
>> From:      0.0.0.0:0
>> To:        <broadcast>:12019
>> Protocol:  UDP
>> Timestamp: 1597904309979
>> ------------------------------------------------------------------
37792
<< ============================== IN ================================
<< From:      0.0.0.0:37792
<< To:        192.168.1.110:46771
<< Protocol:  UDP
<< Timestamp: 1597904309980
<< ------------------------------------------------------------------
{
   "name": "stefano-arch",
   "sharings": [
      {
         "name": "stefano",
         "ftype": "dir",
         "read_only": false
      }
   ],
   "ssl": false,
   "auth": false,
   "rexec": false,
   "version": "0.5",
   "ip": "192.168.1.110",
   "port": 12020,
   "discoverable": true,
   "discover_port": 12019
}
1. stefano-arch (192.168.1.110:12020)
  DIRECTORIES
  • stefano"""

    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_str(justification=15 + 6))
             for info in [
                 CommandOptionInfo(None, params=Trace.T0[0], description=Trace.T0[1]),
                 CommandOptionInfo(None, params=Trace.T1[0], description=Trace.T1[1])
                ]
            ],
            completion=False,
            max_columns=1,
        )


# ============ VERBOSE ================


class Verbose(CommandInfo, OptIntPosArgSpec):
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
**verbose** [*LEVEL*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Change the verbosity level to *LEVEL* (default is *0*, which is disabled).

The messages are written to stdout.

The allowed values of *LEVEL* are:
.A       .
*0*        disabled (default)
*1*        errors
*2*        warnings
*3*        info
*4*        debug
*5*        internal libraries
./A

If no argument is given, increase the verbosity or resets it to *0* \
if it exceeds the maximum."""

    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_str(justification=15 + 6))
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


# ============ ALIAS ================


class Alias(CommandInfo, KeyValArgsSpec):
    def __init__(self):
        super().__init__(optional=True, keepquotes=False)

    @classmethod
    def name(cls):
        return "alias"

    @classmethod
    def short_description(cls):
        return "show or create new command aliases"

    @classmethod
    def synopsis(cls):
        return """\
**alias** [*source*=*target*]\
"""

    @classmethod
    def long_description(cls):
        return """\
If no argument is given, print the current aliases.

An alias can be created using the following syntax:
    **alias** *source*=*target*\
"""

    @classmethod
    def examples(cls):
        return """\
Usage example:

.A .
1. Create an alias
./A
    **/tmp> alias** *s=scan*

.A .
2. Show current aliases
./A
    **/tmp> alias**
    alias s=scan
    alias t=trace
    alias l=ls -la\
"""



# ============ SET ================


class Set(CommandInfo, KeyValArgsSpec):

    VERBOSE = ([Settings.VERBOSITY], "verbosity (from 0 to 5)")
    TRACE = ([Settings.TRACING], "tracing (from 0 to 2)")
    DISCOVER_PORT = ([Settings.DISCOVER_PORT], "discover port")
    DISCOVER_WAIT = ([Settings.DISCOVER_WAIT], "discover timeout (in seconds)")
    SHELL_PASSTHROUGH = ([Settings.DISCOVER_PORT], "whether pass commands to underlying shell")
    COLORS = ([Settings.COLORS], "whether enable styling and colors")


    def __init__(self):
        super().__init__(optional=True, keepquotes=False)

    @classmethod
    def name(cls):
        return "set"

    @classmethod
    def short_description(cls):
        return "show or set easyshare settings"

    @classmethod
    def synopsis(cls):
        return """\
**set** [*setting*=*value*]\
"""

    @classmethod
    def long_description(cls):
        return """\
If no argument is given, print the current settings.

An value can be set using the following syntax:
    **set** *setting*=*value*
    
The allowed settings are the following:
    verbose=<int>
    trace=<int>
    discover_port=<int>
    discover_timeout=<float>
    shell_passthrough=<bool>
    color=<bool>
"""

    @classmethod
    def examples(cls):
        return """\
Usage example:

.A .
1. Set a value
./A
    **/tmp> set** *verbose=4*

.A .
2. Show current settings
./A
    **/tmp> set**
    set verbose=4
    set trace=0\
"""

    @classmethod
    def suggestions(cls, token: str, client) -> Optional[SuggestionsIntent]:
        return SuggestionsIntent(
            [StyledString(info.to_str())
             for info in [
                 CommandOptionInfo(None, params=Set.VERBOSE[0]),
                 CommandOptionInfo(None, params=Set.TRACE[0]),
                 CommandOptionInfo(None, params=Set.DISCOVER_PORT[0]),
                 CommandOptionInfo(None, params=Set.DISCOVER_WAIT[0]),
                 CommandOptionInfo(None, params=Set.SHELL_PASSTHROUGH[0]),
                 CommandOptionInfo(None, params=Set.COLORS[0]),
                 # CommandOptionInfo(None, params=Set.VERBOSE[0], description=Set.VERBOSE[1]),
                 # CommandOptionInfo(None, params=Set.TRACE[0], description=Set.TRACE[1]),
                 # CommandOptionInfo(None, params=Set.DISCOVER_PORT[0], description=Set.DISCOVER_PORT[1]),
                 # CommandOptionInfo(None, params=Set.DISCOVER_WAIT[0], description=Set.DISCOVER_WAIT[1]),
                 # CommandOptionInfo(None, params=Set.SHELL_PASSTHROUGH[0], description=Set.SHELL_PASSTHROUGH[1]),
                 # CommandOptionInfo(None, params=Set.COLORS[0], description=Set.COLORS[1]),

                # TODO: description breaks autocompletion
             ] if info.params[0].startswith(token)
             ],
            completion=True,
            max_columns=1,
            insert_after_completion=lambda s: "="
        )

# ============ xPWD ================


class Pwd(CommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(0, 0)

    @classmethod
    def name(cls):
        return "pwd"

    @classmethod
    def short_description(cls):
        return "show the name of current local working directory"

    @classmethod
    def synopsis(cls):
        return "**pwd**"

    @classmethod
    def long_description(cls):
        return """\
Show the name of current local working directory.

The local working directory can be changed with the command **cd**."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rpwd**" for the remote analogous."""


class Rpwd(CommandInfo, PosArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 0)

    @classmethod
    def name(cls):
        return "rpwd"

    @classmethod
    def short_description(cls):
        return "show the name of current remote working directory"

    @classmethod
    def synopsis(cls):
        return "**rpwd**"

    @classmethod
    def long_description(cls):
        return f"""\
Show the name of current remote working directory.

The remote working directory can be changed with the command **rcd**."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **pwd**" for the local analogous."""

# ============ xLS ================


class BaseLsCommandInfo(CommandInfo, ABC, PosArgsSpec):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    def options_spec(self) -> Optional[List[Option]]:
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

class Ls(LocalAllFilesSuggestionsCommandInfo, BaseLsCommandInfo):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "ls"

    @classmethod
    def short_description(cls):
        return "list local directory content"

    @classmethod
    def synopsis(cls):
        return """\
**ls** [*OPTION*]... [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return """\
List content of the local *DIR* or the current local directory if \
no *DIR* is specified."""

    @classmethod
    def see_also(cls):
        return """Type "**help rls**" for the remote analogous."""

class Rls(RemoteAllFilesSuggestionsCommandInfo, BaseLsCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rls"

    @classmethod
    def short_description(cls):
        return "list remote directory content"

    @classmethod
    def _synopsis(cls):
        return """\
**rls** [*OPTION*]... [*DIR*]

**rls** [*OPTION*]... [*SHARING_LOCATION*] [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return f"""\
List content of the remote DIR or the current remote directory if no DIR \
is specified."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **ls**" for the local analogous."""


# ============ xTREE ================

class BaseTreeCommandInfo(CommandInfo, ABC, PosArgsSpec):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    MAX_DEPTH = ["-d", "--depth"]

    def options_spec(self) -> Optional[List[Option]]:
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


class Tree(BaseTreeCommandInfo, LocalAllFilesSuggestionsCommandInfo):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "tree"

    @classmethod
    def short_description(cls):
        return "list local directory contents in a tree-like format"

    @classmethod
    def synopsis(cls):
        return """\
**tree** [*OPTION*]... [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the local *DIR* or the current \
local directory if no *DIR* is specified."""

    @classmethod
    def examples(cls):
        return """\
Usage example:
    
**/tmp> tree**
|-- dir
|   |-- f1
|   +-- f2
|-- f1
+-- f2"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rtree**" for the remote analogous."""


class Rtree(BaseTreeCommandInfo, RemoteAllFilesSuggestionsCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rtree"

    @classmethod
    def short_description(cls):
        return "list remote directory contents in a tree-like format"

    @classmethod
    def _synopsis(cls):
        return """\
**rtree** [*OPTION*]... [*DIR*]

**rtree** [*OPTION*]... [*SHARING_LOCATION*] [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return """\
List recursively, in a tree-like format, the remote *DIR* or the current \
remote directory if no *DIR* is specified"""

    @classmethod
    def examples(cls):
        return """\
Usage example:
    
**bob-debian.music:/ - /tmp>** **rtree**
|-- dir
|   |-- f1
|   +-- f2
|-- f1
+-- f2"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **tree**" for the local analogous."""


# ============ XFIND ==============


class BaseFindCommandInfo(CommandInfo, ABC, PosArgsSpec):
    NAME = ["-n", "--name"]
    REGEX = ["-r", "--regex"]
    CASE_INSENSITIVE = ["-i", "--insensitive"]
    TYPE = ["-t", "--type"]
    SHOW_DETAILS = ["-l"]
    MAX_DEPTH = ["-d", "--depth"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.NAME, STR_PARAM),
            (self.REGEX, STR_PARAM),
            (self.CASE_INSENSITIVE, PRESENCE_PARAM),
            (self.TYPE, STR_PARAM),
            (self.SHOW_DETAILS, PRESENCE_PARAM),
            (self.MAX_DEPTH, INT_PARAM),
        ]

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.NAME, "filter by filename",
                              params=["pattern"]),
            CommandOptionInfo(cls.REGEX, "filter by filename using regular expression",
                              params=["pattern"]),
            CommandOptionInfo(cls.CASE_INSENSITIVE, "make filename filtering case insensitive"),
            CommandOptionInfo(cls.TYPE, "filter by file type",
                              params=["ftype"]),
            CommandOptionInfo(cls.SHOW_DETAILS, "show more details"),
            CommandOptionInfo(cls.MAX_DEPTH, "maximum display depth of tree", params=["depth"])
        ]

class Find(LocalAllFilesSuggestionsCommandInfo, BaseFindCommandInfo):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "find"

    @classmethod
    def short_description(cls):
        return "search for local files"

    @classmethod
    def synopsis(cls):
        return """\
**find** [*OPTION*]... [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Search for files and directories based on the given filters the local *DIR*, 
or the current local directory if no *DIR* is specified.

Each result of **find** is memorized and can be used further with any command \
that accept local paths by specifying the identifier shown by **find**, which has \
the following syntax:
    $<letter><number>
    
For instance, you can search a file by name (i.e. **find** **-n** *usefulname*) and \
then perform a local action over it (e.g. **rm** $a1) or even a transfer action 
(e.g. **put** $a1).

Furthermore, you can refer to a range of findings using the syntax:
    $<letter><start>:<end>
You can use the range syntax only for commands that support multiple files \
(e.g. **rm** $a4:12).
"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rfind**" for the remote analogous."""

    @classmethod
    def examples(cls):
        return """\
Usage example:

.A .
1. List current local directory (no filters)
./A
    **/tmp> find**
    $a1 FILE2
    $a2 dir1
    $a3 dir1/file
    $a4 dir2
    $a5 file1
    
.A .
2. List local directory (no filters)
./A
    **/tmp> find** *dir1*
    $b3 dir1/file

.A .
3. Finding by name
./A
    **/tmp> find -n** *file*
    $c1 dir1/file
    $c2 file1

.A .
4. Finding by name, case insensitive
./A
    **/tmp> find -in** *file*
    $d1 FILE2
    $d2 dir1/file
    $d3 file1

.A .
5. Finding by regex
./A
    **/tmp> find -r** *file[0-9]*
    $e1 file1

.A .
6. Finding by regex, case insensitive
./A
    **/tmp> find -ir** *file[0-9]*
    $f1 FILE2
    $f2 file1   

.A .
7. Finding by name, files only
./A
    **/tmp> find -in** *dir1* **-t** *f*
    $g1 dir1/file"""



class Rfind(RemoteAllFilesSuggestionsCommandInfo, BaseFindCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rfind"

    @classmethod
    def short_description(cls):
        return "search for remote files"

    @classmethod
    def _synopsis(cls):
        return """\
**rfind** [*OPTION*]... [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Search for files and directories based on the given filters the remote DIR, \
or the current remote directory if no DIR is specified.

Each result of **rfind** is memorized and can be used further with any command \
that accept remote paths by specifying the identifier shown by **find**, which has \
the following syntax:
    $<letter><number>
    
For instance, you can search a file by name (i.e. **rfind** **-n** *usefulname*) and \
then perform a local action over it (e.g. **rrm** $A1) or even a transfer action 
(e.g. **get** $A1).

Furthermore, you can refer to a range of findings using the syntax:
    $<letter><start>:<end>
You can use the range syntax only for commands that support multiple files \
(e.g. **rrm** $A4:12).
"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **find**" for the local analogous."""

    @classmethod
    def examples(cls):
        return """\
Usage example:

.A .
1. List current remote directory (no filters)
./A
    **bob-debian.shared:/ - /tmp> rfind**
    $A1 FILE2
    $A2 dir1
    $A3 dir1/file
    $A4 dir2
    $A5 file1

.A .
2. List remote directory (no filters)
./A
    **bob-debian.shared:/ - /tmp> rfind** *dir1*
    $B3 dir1/file

.A .
3. Finding by name
./A
    **bob-debian.shared:/ - /tmp> rfind** **-n** *file*
    $C1 dir1/file
    $C2 file1

.A .
4. Finding by name, case insensitive
./A
    **bob-debian.shared:/ - /tmp> rfind** **-in** *file*
    $D1 FILE2
    $D2 dir1/file
    $D3 file1

.A .
5. Finding by regex
./A
    **bob-debian.shared:/ - /tmp> rfind** **-r** *file[0-9]*
    $E1 file1

.A .
6. Finding by regex, case insensitive
./A
    **bob-debian.shared:/ - /tmp> rfind** **-ir** *file[0-9]*
    $F1 FILE2
    $F2 file1   

.A .
7. Finding by name, files only
./A
    **bob-debian.shared:/ - /tmp> rfind** **-in** *dir1* **-t** *f*
    $G1 dir1/file"""



# ============ xDU ================


class BaseDuCommandInfo(CommandInfo, ABC, PosArgsSpec):
    HUMAN = ["-h", "--human"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.HUMAN, PRESENCE_PARAM),
        ]

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.HUMAN, "print size in human readable format (e.g. 17K)")
        ]


class Du(LocalAllFilesSuggestionsCommandInfo, BaseDuCommandInfo):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "du"

    @classmethod
    def short_description(cls):
        return "estimate disk usage of local files"

    @classmethod
    def synopsis(cls):
        return """\
**du** *FILE*\
"""

    @classmethod
    def long_description(cls):
        return """\
Estimate the disk usage of *FILE* (which could be either a file or a directory).
If *FILE* is not specified, the disk usage of the current local directory is estimated instead."""

    @classmethod
    def see_also(cls):
        return """Type "**help rdu**" for the remote analogous."""


class Rdu(RemoteAllFilesSuggestionsCommandInfo, BaseDuCommandInfo, FastSharingConnectionCommandInfo):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rdu"

    @classmethod
    def short_description(cls):
        return "estimate disk usage of remote files"

    @classmethod
    def _synopsis(cls):
        return """\
**rdu** [*FILE*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Estimate the disk usage of *FILE* (which could be either a file or a directory).
If *FILE* is not specified, the disk usage of the current remote directory is estimated instead."""

    @classmethod
    def see_also(cls):
        return """Type "**help du**" for the remote analogous."""



# ============ xCD ================


class Cd(LocalDirsOnlySuggestionsCommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(0, 1)

    @classmethod
    def name(cls):
        return "cd"

    @classmethod
    def short_description(cls):
        return "change local working directory"

    @classmethod
    def synopsis(cls):
        return """\
**cd** [*DIR*]"""

    @classmethod
    def long_description(cls):
        return """\
Change the current local working directory to *DIR* or \
to the user's home directory if *DIR* is not specified."""

    @classmethod
    def see_also(cls):
        return """Type "**help rcd**" for the remote analogous."""


class Rcd(RemoteDirsOnlySuggestionsCommandInfo, PosArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    @classmethod
    def name(cls):
        return "rcd"

    @classmethod
    def short_description(cls):
        return "change remote working directory"

    @classmethod
    def synopsis(cls):
        return """\
**rcd** [*DIR*]\
"""

    @classmethod
    def long_description(cls):
        return f"""\
Change the current remote working directory to *DIR* or to the root of the \
current sharing if no *DIR* is specified."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

**/tmp>** open music
**bob-debian.music:/ - /tmp> rcd** *dir*
**bob-debian.music:/dir - /tmp> rcd** *subdir*
**bob-debian.music:/dir/subdir - /tmp>**"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **cd**" for the local analogous."""


# ============ xMKDIR ================


class Mkdir(LocalDirsOnlySuggestionsCommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(1, 0)

    @classmethod
    def name(cls):
        return "mkdir"

    @classmethod
    def short_description(cls):
        return "create a local directory"

    @classmethod
    def synopsis(cls):
        return """\
**mkdir** *DIR*\
"""

    @classmethod
    def long_description(cls):
        return """\
Create the local directory *DIR*.

Parent directories of *DIR* are automatically created when needed.

If *DIR* already exists, it does nothing."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rmkdir**" for the remote analogous."""


class Rmkdir(FastSharingConnectionCommandInfo, RemoteDirsOnlySuggestionsCommandInfo, PosArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory, 0)

    @classmethod
    def name(cls):
        return "rmkdir"

    @classmethod
    def short_description(cls):
        return "create a remote directory"

    @classmethod
    def _synopsis(cls):
        return """\
**rmkdir** *DIR*

**rmkdir** [*SHARING_LOCATION*] *DIR*"""

    @classmethod
    def long_description(cls):
        return f"""\
Create the remote directory *DIR*.

Parent directories of *DIR* are automatically created when needed.

If *DIR* already exists, it does nothing."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

**/tmp>** open music
**bob-debian.music:/ - /tmp> rmkdir** *newdir*
**bob-debian.music:/ - /tmp>** rcd newdir
**bob-debian.music:/newdir - /tmp>**"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **mkdir**" for the local analogous."""


# ============ xCP ================


class Cp(LocalAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self):
        super().__init__(2)

    @classmethod
    def name(cls):
        return "cp"

    @classmethod
    def short_description(cls):
        return "copy files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
**cp** *SOURCE* *DEST*
**cp** *SOURCE*... *DIR*\
"""

    @classmethod
    def long_description(cls):
        return """\
Copy local *SOURCE* file or directory to *DEST*, or copy multiple SOURCEs to the directory *DIR*.

If used with two arguments as "**cp** *SOURCE* *DEST*" the following rules are applied:
.A.
- If *DEST* doesn't exists, *SOURCE* will copied as *DEST*
- If *DEST* exists and it is a directory, *SOURCE* will be copied into *DEST*
- If *DEST* exists and it is a file, *SOURCE* must be a file and it will overwrite *DEST*
./A

If used with at least arguments as "**cp** *SOURCE*... *DIR*" then *DIR* \
must be an existing directory and *SOURCE*s will be copied into it."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rcp**" for the remote analogous."""


class Rcp(FastSharingConnectionCommandInfo, RemoteAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "rcp"

    @classmethod
    def short_description(cls):
        return "copy files and directories remotely"

    @classmethod
    def _synopsis(cls):
        return """\
**rcp** *SOURCE* *DEST*
**rcp** *SOURCE*... *DIR*

**rcp** [*SHARING_LOCATION*] *SOURCE* *DEST*
**rcp** [*SHARING_LOCATION*] *SOURCE*... *DIR*\
"""

    @classmethod
    def long_description(cls):
        return """\
Copy remote *SOURCE* file or directory to *DEST*, or copy multiple *SOURCE*s to \
the directory *DIR*.

If used with two arguments as "**rcp** *SOURCE* *DEST*" the following rules are \
applied:

.A.
- If DEST doesn't exists, SOURCE will copied as DEST
- If DEST exists and it is a directory, SOURCE will be copied into DEST
- If DEST exists and it is a file, SOURCE must be a file and it will overwrite DEST
./A

If used with at least arguments as "**rcp** *SOURCE*... *DIR*" then *DIR* \
must be an existing directory and *SOURCE*s will be copied into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rls
    f1
    **bob-debian.music:/ - /tmp> rcp** *f1* *f2*
    **bob-debian.music:/ - /tmp>** rls
    f1      f2

2.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rtree
    |-- dir
    |-- f1
    +-- f2
    **bob-debian.music:/ - /tmp> rcp** *f1* *f2* *dir*
    **bob-debian.music:/ - /tmp>** rtree
    |-- dir
    |   |-- f1
    |   +-- f2
    |-- f1
    +-- f2"""


    @classmethod
    def see_also(cls):
        return """Type "**help** **cp**" for the local analogous."""



# ============ xMV ================


class Mv(LocalAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self):
        super().__init__(2)

    @classmethod
    def name(cls):
        return "mv"

    @classmethod
    def short_description(cls):
        return "move files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
**mv** *SOURCE* *DEST*
**mv** *SOURCE*... *DIR*\
"""

    @classmethod
    def long_description(cls):
        return """\
Move local *SOURCE* file or directory to *DEST*, or move multiple *SOURCE*s \
to the directory *DIR*.

If used with two arguments as "**mv** *SOURCE* *DEST*" the following rules are applied:
.A.
- If *DEST* doesn't exists, *SOURCE* will moved as *DEST*
- If *DEST* exists and it is a directory, *SOURCE* will be moved into *DEST*
- If *DEST* exists and it is a file, *SOURCE* must be a file and it will overwrite *DEST*
./A

If used with at least arguments as "**mv** *SOURCE*... *DIR*" then *DIR* must be an \
existing directory and *SOURCE*s will be moved into it."""


    @classmethod
    def see_also(cls):
        return """Type "**help** **rmv**" for the remote analogous."""



class Rmv(FastSharingConnectionCommandInfo, RemoteAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "rmv"

    @classmethod
    def short_description(cls):
        return "move files and directories remotely"

    @classmethod
    def _synopsis(cls):
        return """\
**rmv** *SOURCE* *DEST*
**rmv** *SOURCE*... *DIR*

**rmv** [*SHARING_LOCATION*] *SOURCE* *DEST*
**rmv** [*SHARING_LOCATION*] *SOURCE*... *DIR*\
"""

    @classmethod
    def long_description(cls):
        return """\
Move remote *SOURCE* file or directory to *DEST*, or move multiple *SOURCE*s to \
the directory *DIR*.

If used with two arguments as "**rmv** *SOURCE* *DEST*" the following rules are \
applied:

.A.
- If *DEST* doesn't exists, *SOURCE* will moved as *DEST*
- If *DEST* exists and it is a directory, *SOURCE* will be moved into *DEST*
- If *DEST* exists and it is a file, *SOURCE* must be a file and it will overwrite *DEST*
./A

If used with at least arguments as "**rmv** *SOURCE*... *DIR*" then DIR must be an \
existing directory and *SOURCE*s will be moved into it."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rls
    f1
    **bob-debian.music:/ - /tmp>** **rmv** *f1* *f2*
    **bob-debian.music:/ - /tmp>** rls
    f2

2.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rtree
    |-- dir
    |-- f1
    +-- f2
    **bob-debian.music:/ - /tmp>** **rmv** *f1* *f2* *dir*
    **bob-debian.music:/ - /tmp>** rtree dir
    +-- dir
        |-- f1
        +-- f2"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **mv**" for the local analogous."""


# ============ xRM ================


class Rm(LocalAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self):
        super().__init__(1)

    @classmethod
    def name(cls):
        return "rm"

    @classmethod
    def short_description(cls):
        return "remove files and directories locally"

    @classmethod
    def synopsis(cls):
        return """\
**rm** [*FILE*]...\
"""

    @classmethod
    def long_description(cls):
        return """\
Remove local *FILE*s.

If a *FILE* is a directory, it will be removed recursively.

If a *FILE* does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rrm**" for the remote analogous."""



class Rrm(FastSharingConnectionCommandInfo, RemoteAllFilesSuggestionsCommandInfo, VarArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "rrm"

    @classmethod
    def short_description(cls):
        return "remove files and directories remotely"

    @classmethod
    def _synopsis(cls):
        return """\
**rrm** [*FILE*]...

**rrm** [*SHARING_LOCATION*] [*FILE*]...\
"""

    @classmethod
    def long_description(cls):
        return """\
Remove remote *FILE*s.

If a *FILE* is a directory, it will be removed recursively.

If a *FILE* does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rls
    f1      f2
    **bob-debian.music:/ - /tmp>** **rrm** *f2*
    **bob-debian.music:/ - /tmp>** <rls
    f1

2.
    **/tmp>** open music
    **bob-debian.music:/ - /tmp>** rtree
    |-- dir
    |   |-- f1
    |   +-- f2
    +-- f1
    **bob-debian.music:/ - /tmp>** **rrm** *dir*
    **bob-debian.music:/ - /tmp>** rtree
    +-- f1"""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rm**" for the local analogous."""

# ============ xSHELL ===============

class Shell(LocalAllFilesSuggestionsCommandInfo, StopParseArgsSpec, KeepQuotesArgsSpec):
    def __init__(self):
        super().__init__(0)

    @classmethod
    def name(cls):
        return "shell"

    @classmethod
    def short_description(cls):
        return "start a local shell or execute a command"

    @classmethod
    def synopsis(cls):
        return """\
**shell** [*COMMAND*]\
"""

    @classmethod
    def long_description(cls):
        return """\
If no *COMMAND* is given, start a local shell using the user's preferred shell.

Differently from **exec**, this really opens a pseudo terminal (ssh style).

If *COMMAND* is given, it is executed on the pseudo terminal (but you won't \
get a shell unless *COMMAND* is a shell itself)

Currently supported only if the server is Unix."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **rshell**" for the remote analogous."""


class Rshell(FastSharingConnectionCommandInfo, RemoteAllFilesSuggestionsCommandInfo,
             StopParseArgsSpec, KeepQuotesArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "rshell"

    @classmethod
    def short_description(cls):
        return "start a remote shell or execute a command"

    @classmethod
    def _synopsis(cls):
        return """\
**rshell** [*COMMAND]*

**rshell** [*SERVER_LOCATION*] [*COMMAND*]\
"""

    @classmethod
    def long_description(cls):
        return """\
If no *COMMAND* is given, start a remote shell using the remote user's \
preferred shell.

If *COMMAND* is given, it is executed on the pseudo terminal (but you won't \
get a shell, unless *COMMAND* is a shell itself)

Currently supported only if the server is Unix."""

    @classmethod
    def see_also(cls):
        return """Type "**help** **shell**" for the local analogous."""



# ============ SCAN ================


class Scan(CommandInfo, NoPosArgsSpec):
    SHOW_SHARINGS_DETAILS = ["-l"]
    SHOW_ALL_DETAILS = ["-L"]

    def options_spec(self) -> Optional[List[Option]]:
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
**scan** [*OPTION*]..."""

    @classmethod
    def long_description(cls):
        return """\
Scan the network for easyshare server and reports the details of the \
sharings found.

The discover is performed in broadcast in the network.

The port on which the discover is performed is the one specified to **es** \
via **-d** *port*, or the default one if not specified.

The scan time is two seconds unless it has been specified to **es** \
via **-w** *seconds*.

Only details about the sharings are shown, unless **-L** is given."""

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

**/tmp> scan**
alice-arch (192.168.1.105:12020)
  DIRECTORIES
  - shared
  - tmp
bob-debian (192.168.1.185:12020)
  DIRECTORIES
  - music
  FILES
  - README.txt"""


# ============ CONNECT ================


class Connect(CommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(1)

    @classmethod
    def name(cls):
        return "connect"

    @classmethod
    def short_description(cls):
        return "connect to a remote server"

    @classmethod
    def synopsis(cls):
        return """\
**connect** *SERVER_LOCATION*\
"""

    @classmethod
    def long_description(cls):
        return """\
Connect to a remote server whose location is specified by *SERVER_LOCATION*.

*SERVER_LOCATION* has the following syntax:
    <*server_name*> or <*address*>[:<*port*>]

See the section **EXAMPLES** for more examples about *SERVER_LOCATION*.

The following rules are applied for establish a connection:
.A .
1. If *SERVER_LOCATION* is a valid <*server_name*> (e.g. alice-arch), \
a discover is performed for figure out which port the server is bound to.
2. If *SERVER_LOCATION* has the form <*address*> (e.g. 192.168.1.105), the \
connection will be tried to be established directly to the server at the \
default port. If the attempt fails, a discover is performed for figure \
out which port the server is really bound to and another attempt is done.
3. If *SERVER_LOCATION* has the form <*address*>:<*port*> (e.g, 182.168.1.106:22020), \
the connection will be established directly.
./A

The discover, if involved (1. and 2.), is performed on the port specified \
to **es** with **-d** *port* for the time specified with **-w** *seconds* \
(default is two seconds).

Note that **connect** is not necessary if you want to directly open a sharing, \
you can use **open** which automatically will establish the connection with the \
server as connect would do.

There might be cases in which use **connect** is still required, for example for \
execute server commands (i.e. info, ping, list, rexec) which are not related \
to any sharings (you can use those commands if connected to a sharing, by the way).

When possible, using "**connect** <*server_name*>" (1.) is more immediate and \
human friendly compared to specify the address and eventually the port of the \
server (2. and 3.).

There are cases in which specify the address and the port of the server (3.) \
is necessary, for example when the discover can't be performed because the \
server is not on the same network of the client (e.g. behind a NAT).

If already connected to a server, a successful **connect** execution to another \
server automatically closes the current connection.

Remember that **connect** establish the connection with the server, but do not \
place you inside any server's sharing. Use **open** for that."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1. Connection by server name (discover)
    **/tmp> connect** *alice-arch*
    **alice-arch - /tmp>** list
    DIRECTORIES
    - shared
    - tmp

    2. Connection by address (direct attempt, discover if fails)
    **/tmp> connect** *192.168.1.105*
    **alice-arch - /tmp>**

3. Connection by address and port (direct)
    **/tmp> connect** *89.1.2.84:22020*
    **eve-kali - /tmp>**"""

    @classmethod
    def see_also(cls):
        return "**disconnect**, **open**"


# ============ DISCONNECT ================


class Disconnect(CommandInfo, PosArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "disconnect"

    @classmethod
    def short_description(cls):
        return "disconnect from a remote server"

    @classmethod
    def synopsis(cls):
        return """\
**disconnect**\
"""

    @classmethod
    def long_description(cls):
        return """\
Disconnect from the remote server to which the connection is established.

While this command is the counterpart of **connect**, it can be used to \
close connections opened in other ways (i.e. with **open**).

This differs from **close** which closes only the currently opened sharing \
without closing the connection."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

**/tmp>** connect alice-arch
**alice-arch - /tmp> disconnect**
**/tmp>** connect"""

    @classmethod
    def see_also(cls):
        return "**connect**, **close**"


# ============ OPEN ================


class Open(CommandInfo, PosArgsSpec):
    def __init__(self):
        super().__init__(1)

    @classmethod
    def name(cls):
        return "open"

    @classmethod
    def short_description(cls):
        return "open a remote sharing (eventually discovering it)"

    @classmethod
    def synopsis(cls):
        return """\
**open** *SHARING_LOCATION*\
"""

    @classmethod
    def long_description(cls):
        return """\
Open a sharing whose location is specified by *SHARING_LOCATION*

*SHARING_LOCATION* has the following syntax:
    <*sharing_name*>[@<*server_name*>|<*address*>[:<*port*>]]

See the section **EXAMPLES** for more examples about *SHARING_LOCATION*.

The following rules are applied for establish a connection:

.A .
1. If *SHARING_LOCATION* is a valid <*sharing_name*> (e.g. shared), a discover \
is performed for figure out to which server the sharing belongs to.
2. If *SHARING_LOCATION* has the form <*sharing_name*>@<*server_name*>[:*port*] \
(e.g. shared@alice-arch) a discover is performed as well as in case 1. and \
the <*server_name*> and the <*port*> act only as a filter (i.e. the connection \
won't be established if they don't match).
3. If *SHARING_LOCATION* has the form <*sharing_name*>@<*address*> \
(e.g. shared@192.168.1.105) the connection will be tried to be established \
directly to the server at the default port. If the attempt fails, a discover \
is performed for figure out which port the server is really bound to and \
another attempt is done.
4. If *SHARING_LOCATION* has the form <*sharing_name*>@<*address*>:<*port*> \
(e.g. shared@192.168.1.105:12020) the connection will be established directly.
./A

The discover, if involved (1., 2. and 3.), is performed on the port \
specified to es with **-d** *port* for the time specified with **-w** *seconds* \
(default is two seconds).

Note that **connect** is not necessary if you want to directly open a sharing, \
you can use open which automatically will establish the connection with the \
server as **connect** would do.

When possible, using the server name (1., 2. and 3.) is more immediate and \
human friendly compared to specify the address and eventually the port of \
the server (4.).

There are cases in which specify the address and the port of the server \
(4.) is necessary, for example when the discover can't be performed because the \
server is not on the same network of the client (e.g. behind a NAT).

If the sharing described by *SHARING_LOCATION* is found within the sharings of \
the server to which the connection is already established, it will be \
obviously opened without perform any kind of discover or new connection.

If already connected to a server and/or a sharing, a successful **open** \
execution to another server automatically closes the current connection.

If, for some reason, there is more than a sharing with the same name on the \
same network, **open** will try to connect to the one that is discovered first \
(in general it's unpredictable which will be).

If you need a deterministic (and more safe) approach, consider using **scan** for \
discover the server manually (eventually followed by a consecutive **info** \
call for fetch more accurate details such as SSL certificate) then invoke **open** \
specifying the server details too (i.e. server name or address and port).

In general, **open** doesn't require you to use **connect** before; the connection \
will be created for you automatically."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

.A .
1. Connection by sharing name (while connected)
./A
    **/tmp>** connect alice-arch
    **alice-arch - /tmp> open** *temp*
    **alice-arch.temp:/ - /tmp>** rls
    f1      f2

.A .
1b. Connection by sharing name (discover)
./A
    **/tmp> open** *temp*
    **alice-arch.temp:/ - /tmp>** rls
    f1      f2

.A .
2. Connection by sharing name with server name filter (discover)
./A
    **/tmp> open** *temp@alice-arch*
    **alice-arch.temp:/ - /tmp>**

.A .
3. Connection by sharing name with address (attempt direct, discover if fails)
./A
    **/tmp> open** *temp@alice-arch*
    **alice-arch.temp:/ - /tmp>**

.A .
4. Connection by sharing name with address and port (direct)
./A
    **/tmp> open** *temp@192.168.1.105:12020*
    **alice-arch.temp:/ - /tmp>**"""

    @classmethod
    def see_also(cls):
        return "**close**, **connect**"


# ============ CLOSE ================


class Close(CommandInfo, PosArgsSpec):
    def __init__(self, mandatory: int):
        super().__init__(mandatory)

    @classmethod
    def name(cls):
        return "close"

    @classmethod
    def short_description(cls):
        return "close the remote sharing"

    @classmethod
    def synopsis(cls):
        return """\
**close**"""

    @classmethod
    def long_description(cls):
        return """\
Close the currently opened sharing.

If the sharing connection has been created directly with **open** instead of \
**connect** and then **open**, than the server connection is closed too (for symmetry)."""

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

1. Close sharing connection only
    **/tmp>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp> close**
    **alice-arch - /tmp> close**

2. Close both sharing and server connection
    **/tmp>** open music
    **bob-debian.music:/ - /tmp> close**
    **/tmp>**"""

    @classmethod
    def see_also(cls):
        return "**open**, **disconnect**"


# ============ GET ================


class Get(RemoteAllFilesSuggestionsCommandInfo, VarArgsSpec):
    OVERWRITE_YES = ["-y", "--overwrite-yes"]
    OVERWRITE_NO = ["-n", "--overwrite-no"]
    OVERWRITE_NEWER = ["-N", "--overwrite-newer"]
    OVERWRITE_DIFF_SIZE = ["-S", "--overwrite-diff-size"]
    PREVIEW = ["-p", "--preview"]
    CHECK = ["-c", "--check"]
    QUIET = ["-q", "--quiet"]
    NO_HIDDEN = ["-h", "--no-hidden"]
    SYNC = ["-s", "--sync"]

    # Secret params
    MMAP = ["--mmap"]
    CHUNK_SIZE = ["--chunk-size"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.OVERWRITE_YES, PRESENCE_PARAM),
            (self.OVERWRITE_NO, PRESENCE_PARAM),
            (self.OVERWRITE_NEWER, PRESENCE_PARAM),
            (self.OVERWRITE_DIFF_SIZE, PRESENCE_PARAM),
            (self.PREVIEW, PRESENCE_PARAM),
            (self.CHECK, PRESENCE_PARAM),
            (self.QUIET, PRESENCE_PARAM),
            (self.NO_HIDDEN, PRESENCE_PARAM),
            (self.SYNC, PRESENCE_PARAM),

            (self.MMAP, INT_PARAM),
            (self.CHUNK_SIZE, INT_PARAM),
        ]

    @classmethod
    def name(cls):
        return "get"

    @classmethod
    def short_description(cls):
        return "get files and directories from the remote sharing"

    @classmethod
    def synopsis(cls):
        return """\
**get** [*OPTION*]... [*REMOTE_FILE*]...

**get** [*OPTION*]... [*SHARING_LOCATION*] [*REMOTE_FILE*]..."""

    @classmethod
    def long_description(cls):
        return """\
Get files and directories from a remote sharing to the local machine.

This command can be used for two similar purpose:
.A .
1. Download either files or directory from a "directory sharing"
2. Download a "file sharing" (i.e. a single file with a sharing name assigned to it).
./A

In case 1. a connection to the remote sharing have to be established in \
one of the following manners:
.A .
1a. Create a connection to the sharing with connect and/or open
1b. Provide a SHARING_LOCATION to the get command (e.g. get alice-arch temp)
./A

If execute while connected to a "directory sharing" (1.) the following \
rules are applied:
.A.
- If *REMOTE_FILE*s arguments are given, then the specified remote files are 
  downloaded into the local directory
- If no *REMOTE_FILE* argument is given, then the entire sharing is downloaded \
into the local directory within a folder that has he same name as the sharing
- If *REMOTE_FILE* is "\*", then the entire sharing is downloaded into the local \
directory (without wrapping it into a folder)
./A

For download a "file sharing" (2.), **get** must be used in the form \
"**get** [*SHARING_LOCATION*]" (e.g. get alice-arch file) and there is no \
need to **open** the sharing before (since it's a file), as in case 1. 

*REMOTE_FILE* can be:
.A.
- a path relative to the current remote working directory \
(**rpwd**), (e.g. afile, adir/afile)
- a path absolute with respect to the sharing root, \
which is defined by a leading slash (e.g. /f1)
./A

The files will be placed into the current local directory (which can be \
changed with **cd**, inside or outside **es** shell).

Directories are automatically downloaded recursively.

If a remote file has the same name of a local file, you will be asked \
whether overwrite it or not. The default overwrite behaviour can be specified \
with the options **-y** (yes), **-n** (no), **-N** (overwrite if newer) and **-S** \
(overwrite if size is different)."""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.OVERWRITE_YES, "always overwrite files"),
            CommandOptionInfo(cls.OVERWRITE_NO, "never overwrite files"),
            CommandOptionInfo(cls.OVERWRITE_NEWER, "overwrite files only if newer"),
            CommandOptionInfo(cls.OVERWRITE_DIFF_SIZE, "overwrite files only if size is different"),
            CommandOptionInfo(cls.PREVIEW, "do not transfer, just show a preview of what will happen"),
            CommandOptionInfo(cls.CHECK, "performs a check of files consistency"),
            CommandOptionInfo(cls.QUIET, "doesn't show progress"),
            CommandOptionInfo(cls.NO_HIDDEN, "doesn't copy hidden files"),
            CommandOptionInfo(cls.SYNC, "synchronize (same as -N but remove old files)"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
.A .
1. Get all the content of a directory sharing (wrapped into a folder)
./A
    **/tmp>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    +-- f2
    **alice-arch.shared:/ - /tmp>** rls
    f_remote_1
    **alice-arch.shared:/ - /tmp> get**
    GET shared/f_remote_1    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    |-- f2
    +-- shared
        +-- f_remote_1

.A .
2. Get all the content of a directory sharing (into the current directory)
./A
    **/tmp>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    +-- f2
    **alice-arch.shared:/ - /tmp>** rls
    f_remote_1
    **alice-arch.shared:/ - /tmp>** **get** *\**
    GET f_remote_1    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    |-- f2
    +-- f_remote_1

.A .
3. Get specific files from a directory sharing
./A
    **/tmp>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    +-- f2
    **alice-arch.shared:/ - /tmp>** rls
    f_remote_1      f_remote_2      f_remote_another
    **alice-arch.shared:/ - /tmp> get** *f_remote_1* *f_remote_2*
    GET f_remote_1    [===================] 100%  745KB/745KB
    GET f_remote_2    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        2  (1.4MB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp>** tree
    |-- f1
    |-- f2
    |-- f_remote_1
    +-- f_remote_2

.A .
4. Get without establish a connection before
./A
    **/tmp>** tree
    |-- f1
    +-- f2
    **/tmp> get** *shared*
    GET f_remote_1    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    **/tmp>** tree
    |-- f1
    |-- f2
    +-- shared
        +-- f_remote_1

.A .
5. Get a file sharing (without establish a connection before)
./A
    **/tmp>** tree
    |-- f1
    +-- f2
    **/tmp> get** *f_share*
    GET f_share    [===================] 100%  745KB/745KB
    GET outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    **/tmp>** tree
    |-- f1
    |-- f2
    +-- f_share"""

    @classmethod
    def see_also(cls):
        return "**open**, **put**"



# ============ PUT ================


class Put(LocalAllFilesSuggestionsCommandInfo, VarArgsSpec):
    OVERWRITE_YES = ["-y", "--overwrite-yes"]
    OVERWRITE_NO = ["-n", "--overwrite-no"]
    OVERWRITE_NEWER = ["-N", "--overwrite-newer"]
    OVERWRITE_DIFF_SIZE = ["-S", "--overwrite-diff-size"]
    PREVIEW = ["-p", "--preview"]
    CHECK = ["-c", "--check"]
    QUIET = ["-q", "--quiet"]
    NO_HIDDEN = ["-h", "--no-hidden"]
    SYNC = ["-s", "--sync"]


    # Secret params
    MMAP = ["--mmap"]
    CHUNK_SIZE = ["--chunk-size"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.OVERWRITE_YES, PRESENCE_PARAM),
            (self.OVERWRITE_NO, PRESENCE_PARAM),
            (self.OVERWRITE_NEWER, PRESENCE_PARAM),
            (self.OVERWRITE_DIFF_SIZE, PRESENCE_PARAM),
            (self.PREVIEW, PRESENCE_PARAM),
            (self.CHECK, PRESENCE_PARAM),
            (self.QUIET, PRESENCE_PARAM),
            (self.NO_HIDDEN, PRESENCE_PARAM),
            (self.SYNC, PRESENCE_PARAM),

            (self.MMAP, INT_PARAM),
            (self.CHUNK_SIZE, INT_PARAM),
        ]

    @classmethod
    def name(cls):
        return "put"

    @classmethod
    def short_description(cls):
        return "put files and directories to the remote sharing"

    @classmethod
    def synopsis(cls):
        return """\
**put** [*OPTION*]... [*LOCAL_FILE*]...

**put** [*OPTION*]... [*SHARING_LOCATION*] [*LOCAL_FILE*]...\
"""

    @classmethod
    def long_description(cls):
        return """\
Put files and directories into a remote sharing.

The remote sharing must be of type "directory sharing", otherwise **put** will 
fail.

The connection to the remote sharing have to be established in one of the \
following manners:
.A.
- Create a connection to the sharing with **connect** and/or **open**
- Provide a *SHARING_LOCATION* to the **put** command (e.g. put alice-arch f1)
./A

If execute while connected to a "directory sharing" (1.) the following \
rules are applied:
.A.
- If *LOCAL_FILE*s arguments are given, then the specified local files are \
uploaded into the remote directory
- If no *LOCAL_FILE* argument is given, then the entire local folder is \
uploaded into the remote sharing within a folder that has he same name as the \
folder
- If *LOCAL_FILE* is "\*", then the entire local folder is uploaded into the \
remote sharing (without wrapping it into a folder)
./A

*LOCAL_FILE* must be a path to a local valid file or directory, either \
relative or absolute.

The files will be placed into the current remote directory (which can be \
changed with **rcd**).
The default remote directory is the root of the "directory sharing".

Directories are automatically uploaded recursively.

If a remote file has the same name of a local file, you will be asked \
whether overwrite it or not. The default overwrite behaviour can be \
specified with the options **-y** (yes), **-n** (no), **-N** (overwrite if newer) \
and **-S** (overwrite if size is different)."""
    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.OVERWRITE_YES, "always overwrite files"),
            CommandOptionInfo(cls.OVERWRITE_NO, "never overwrite files"),
            CommandOptionInfo(cls.OVERWRITE_NEWER, "overwrite files only if newer"),
            CommandOptionInfo(cls.OVERWRITE_DIFF_SIZE, "overwrite files only if size is different"),
            CommandOptionInfo(cls.PREVIEW, "do not transfer, just show a preview of what will happen"),
            CommandOptionInfo(cls.CHECK, "performs a check of files consistency"),
            CommandOptionInfo(cls.QUIET, "doesn't show progress"),
            CommandOptionInfo(cls.NO_HIDDEN, "doesn't copy hidden files"),
            CommandOptionInfo(cls.SYNC, "synchronize (same as -N but remove old files)"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
.A .
1. Put all the content of a directory into a sharing (wrapped into a folder)
./A
    **/tmp/localdir>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp/localdir>** tree
    |-- f1
    +-- f2
    **alice-arch.shared:/ - /tmp/localdir>** rls
    f_remote_1
    **alice-arch.shared:/ - /tmp/localdir>** **put**
    PUT localdir/f1    [===================] 100%  745KB/745KB
    PUT localdir/f2    [===================] 100%  745KB/745KB
    PUT outcome: OK
    Files        2  (1.4MB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp/localdir>** rtree
    |-- f_remote_1
    +-- localdir
        |-- f1
        +-- f2

.A .
2. Put all the content of a directory into a sharing (not wrapped into a folder)
./A
    **/tmp/localdir>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp/localdir>** tree
    |-- f1
    +-- f2
    **alice-arch.shared:/ - /tmp/localdir>** rls
    f_remote_1
    **alice-arch.shared:/ - /tmp/localdir>** **put** *\**
    PUT f1    [===================] 100%  745KB/745KB
    PUT f2    [===================] 100%  745KB/745KB
    PUT outcome: OK
    Files        2  (1.4MB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp/localdir>** rtree
    |-- f_remote_1
    |-- f1
    +-- f2

.A .
3. Put specific files into a sharing (not wrapped into a folder)
./A
    **/tmp/localdir>** connect alice-arch
    **alice-arch - /tmp>** open shared
    **alice-arch.shared:/ - /tmp/localdir>** tree
    |-- f1
    |-- f2
    +-- f3
    **alice-arch.shared:/ - /tmp/localdir>** rls
    f_remote_1
    **alice-arch.shared:/ - /tmp/localdir>** **put** *f1* *f2*
    PUT f1    [===================] 100%  745KB/745KB
    PUT f2    [===================] 100%  745KB/745KB
    PUT outcome: OK
    Files        2  (1.4MB)
    Time         1s
    Avg. speed   1MB/s
    **alice-arch.shared:/ - /tmp/localdir>** rtree
    |-- f_remote_1
    |-- f1
    +-- f2

.A .
4. Put without establish a connection before
./A
    **/tmp/localdir> put** *shared* *f1*
    PUT f1    [===================] 100%  745KB/745KB
    PUT outcome: OK
    Files        1  (745KB)
    Time         1s
    Avg. speed   1MB/s
    /tmp/localdir> rtree shared
    +-- f1"""

    @classmethod
    def see_also(cls):
        return "**open**, **get**"



# ============ LIST ================


class ListSharings(FastServerConnectionCommandInfo, PosArgsSpec):
    @classmethod
    def name(cls):
        return "list"

    @classmethod
    def short_description(cls):
        return "list the sharings of the remote server"

    @classmethod
    def _synopsis(cls):
        return """\
**list**...

**list** [*SERVER_LOCATION*]...\
"""

    @classmethod
    def long_description(cls):
        return """\
List the sharings of the remote server to which the connection is established."""


    @classmethod
    def examples(cls):
        return f"""\
Usage example:

**/tmp>** connect alice-arch
**alice-arch** - **/tmp>** **list**
DIRECTORIES
- shared
- tmp

**/tmp>** open music
**bob-debian.music:/** - **/tmp>** **list**
DIRECTORIES
- music
FILES
- README.txt"""


# ============ INFO ================


class Info(FastServerConnectionCommandInfo, PosArgsSpec):
    SHOW_ONLY_SHARINGS = ["-s", "--sharings"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.SHOW_ONLY_SHARINGS, PRESENCE_PARAM),
        ]

    @classmethod
    def name(cls):
        return "info"

    @classmethod
    def short_description(cls):
        return "show information about the remote server"

    @classmethod
    def _synopsis(cls):
        return """\
**info** [*OPTION*]...

info [*SERVER_LOCATION*] [*OPTION*]...\
"""

    @classmethod
    def long_description(cls):
        return """\
Show information of the remote server to which the connection is established.

The reported information are: 
- Server version
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
            CommandOptionInfo(cls.SHOW_ONLY_SHARINGS, "show only sharings information"),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:

**/tmp>** connect alice-arch
**alice-arch - /tmp> info**
================================

SERVER INFO

Name:             alice-arch
Address:          192.168.1.105
Port:             12020
Discoverable:     True
Discover Port:    12019
Authentication:   False
SSL:              True
Remote execution: disabled
Version:          0.6

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


class Ping(FastServerConnectionCommandInfo, PosArgsSpec):
    COUNT = ["-c", "--count"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.COUNT, INT_PARAM),
        ]

    @classmethod
    def name(cls):
        return "ping"

    @classmethod
    def short_description(cls):
        return "test the connection with the remote server"

    @classmethod
    def _synopsis(cls):
        return """\
**ping** [*OPTION*]...

**ping** [*OPTION*]... [*SERVER_LOCATION*]\
"""

    @classmethod
    def long_description(cls):
        return """\
Test the connectivity with the server by sending application-level messages."""

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.COUNT, "stop after *count* messages", ["count"]),
        ]

    @classmethod
    def examples(cls):
        return f"""\
Usage example:
    
1.
    **/tmp>** connect alice-arch
    **alice-arch - /tmp> ping**
    [1] PONG from alice-arch (192.168.1.105:12020)  |  time=5.1ms
    [2] PONG from alice-arch (192.168.1.105:12020)  |  time=0.9ms
    \.\.\.
    
2.
    **/tmp> ping** *bob-debian* **-c** *1*
    [1] PONG from bob-debian (192.168.1.185:12020)  |  time=9.3ms

3.
    **/tmp> ping** *192.168.1.185* **-c** *1*
    [1] PONG from bob-debian (192.168.1.185:12020)  |  time=10.3ms"""


# Maps command name -> command info

COMMANDS_INFO: Dict[str, Type[CommandInfo]] = {
    Commands.HELP: Help,
    Commands.EXIT: Exit,
    Commands.QUIT: Exit,

    Commands.TRACE: Trace,
    Commands.VERBOSE: Verbose,

    Commands.ALIAS: Alias,
    Commands.SET: Set,

    Commands.LOCAL_CURRENT_DIRECTORY: Pwd,
    Commands.LOCAL_LIST_DIRECTORY: Ls,
    Commands.LOCAL_TREE_DIRECTORY: Tree,
    Commands.LOCAL_FIND: Find,
    Commands.LOCAL_DISK_USAGE: Du,
    Commands.LOCAL_CHANGE_DIRECTORY: Cd,
    Commands.LOCAL_CREATE_DIRECTORY: Mkdir,
    Commands.LOCAL_COPY: Cp,
    Commands.LOCAL_MOVE: Mv,
    Commands.LOCAL_REMOVE: Rm,
    Commands.LOCAL_SHELL: Shell,

    Commands.REMOTE_CURRENT_DIRECTORY: Rpwd,
    Commands.REMOTE_LIST_DIRECTORY: Rls,
    Commands.REMOTE_TREE_DIRECTORY: Rtree,
    Commands.REMOTE_FIND: Rfind,
    Commands.REMOTE_DISK_USAGE: Rdu,
    Commands.REMOTE_CHANGE_DIRECTORY: Rcd,
    Commands.REMOTE_CREATE_DIRECTORY: Rmkdir,
    Commands.REMOTE_COPY: Rcp,
    Commands.REMOTE_MOVE: Rmv,
    Commands.REMOTE_REMOVE: Rrm,
    Commands.REMOTE_SHELL: Rshell,

    Commands.SCAN: Scan,

    Commands.CONNECT: Connect,
    Commands.DISCONNECT: Disconnect,

    Commands.OPEN: Open,
    Commands.CLOSE: Close,

    Commands.GET: Get,
    Commands.PUT: Put,

    Commands.INFO: Info,
    Commands.LIST: ListSharings,
    Commands.PING: Ping,
}