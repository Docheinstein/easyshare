import mmap
import os
import re
import select
import signal
import sys
import threading
import time
import zlib
from collections import OrderedDict, deque
from getpass import getpass
from pathlib import Path
from typing import Optional, Callable, List, Dict, Union, Tuple, cast, Any, Deque
from easyshare.utils.progress import ProgressBarRendererFactory
from easyshare.args import Args as Args, ArgsParseError, ArgsSpec
from easyshare.common import DEFAULT_SERVER_PORT, SUCCESS_COLOR, PROGRESS_COLOR, BEST_BUFFER_SIZE, \
    ERROR_COLOR, APP_VERSION
from easyshare.consts import ansi
from easyshare.consts.net import ADDR_BROADCAST
from easyshare.consts.os import STDIN
from easyshare.endpoint import Endpoint
from easyshare.es.common import ServerLocation, SharingLocation
from easyshare.es.connection import Connection, ConnectionMinimal
from easyshare.es.discover import Discoverer
from easyshare.es.errors import ClientErrors, ErrorsStrings, errno_str, print_errors, outcome_str, AnyErrs
from easyshare.es.ui import print_files_info_list, print_files_info_tree, \
    sharings_pretty_str, server_info_short_str, file_info_inline_sstr, StyledString, \
    file_info_pretty_str, server_pretty_str, file_info_pretty_sstr
from easyshare.commands.commands import Commands, Ls, Scan, Info, Tree, Put, Get, \
    Ping, Find, Rfind, Du, Rdu, Rls, Cd, Mkdir, Pwd, Rm, Mv, Cp, Shell, Rcd, Rtree, Rmkdir, \
    Rpwd, Rrm, Rmv, Rcp, Rshell, Connect, Disconnect, Open, Close, ListSharings, Stat, Rstat
from easyshare.logging import get_logger
from easyshare.protocol.requests import RequestsParams, RequestParams
from easyshare.protocol.responses import is_data_response, is_error_response, is_success_response, ResponseError, \
    create_error_of_response, ResponsesParams, Response
from easyshare.protocol.types import FileType, ServerInfoFull, FileInfoTreeNode, FileInfo, FTYPE_DIR, FTYPE_FILE, \
    ServerInfo, create_file_info, RexecEventType, ftype_of, create_file_info_full
from easyshare.settings import get_setting, Settings
from easyshare.styling import bold, green, red
from easyshare.timer import Timer
from easyshare.utils.env import is_unix, terminal_size
from easyshare.utils.json import j
from easyshare.utils.measures import duration_str_human, speed_str, size_str, size_str_justify
from easyshare.utils.os import ls, rm, tree, mv, cp, user, pty_attached, os_error_str, \
    find, du, set_mtime
from easyshare.utils.path import LocalPath, is_hidden
from easyshare.utils.progress.file import FileProgressor
from easyshare.utils.progress.simple import SimpleProgressor
from easyshare.utils.str import q, chrnext
from easyshare.utils.types import itob, btoi


if is_unix():
    import pty
    import tty
    from pwd import struct_passwd


log = get_logger(__name__)


def formatted_errors_from_error_response(resp: Response) -> Optional[List]:
    """
    Returns an array of strings built from the resp errors
    (which contains either strings and err [+params].
    """
    if not is_error_response(resp):
        return None

    errors = resp.get("errors")
    if not errors:
        return None

    # For each error build a formatted string using the subjects, if any
    return [formatted_error_from_error_of_response(er) for er in errors]

def formatted_error_from_error_of_response(resp_err: ResponseError) -> str:
    """
    Returns a formatted string based on the 'errno' and the 'sujects' of resp_err'
    """
    errno = resp_err.get("errno")
    subjects = resp_err.get("subjects")

    if subjects:
        return errno_str(errno, *subjects)
    return errno_str(errno)


def ensure_success_response(resp: Response):
    if not resp:
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

    if is_error_response(resp):
        raise CommandExecutionError(formatted_errors_from_error_response(resp))
    if not is_success_response(resp):
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)


def ensure_data_response(resp: Response, *data_fields) -> Any:
    if not resp:
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

    if is_error_response(resp):
        raise CommandExecutionError(formatted_errors_from_error_response(resp))
    if not is_data_response(resp):
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

    resp_data = resp.get("data")

    for data_field in data_fields:
        if data_field not in resp_data:
            raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
    return resp_data

def make_sharing_connection_api_wrapper(api, ftype: Optional[FileType]):
    def wrapper(client: 'Client', args: Args, _1: Connection):
        # Wraps api providing the connection parameters.
        # The provided connection is the client current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if connection exists before invoking %s", api.__name__)

        was_connected_to_server = client.is_connected_to_server()
        was_connected_to_sharing = client.is_connected_to_sharing()

        conn = \
            client._get_current_sharing_connection_or_create_from_sharing_location_args(args, ftype)

        # Server connection must be valid
        if not conn or not conn.is_connected_to_server():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Sharing connection must be valid, if ftype is DIR
        if ftype == FTYPE_DIR and not conn.is_connected_to_sharing():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Method call

        log.d("Connection established, invoking %s", api.__name__)
        api(client, args, conn)

        # Cleanup

        if conn == client.connection:
            if not was_connected_to_sharing:
                log.d("Closing temporary sharing connection")
                client.close()
                # conn.close()
        elif conn.is_connected_to_server():
            # check again since some api might destroy the connection in
            # the meanwhile (e.g. get/put if CTRL+C is pressed in the meanwhile)
            log.d("Disconnecting temporary server connection")
            conn.disconnect()

    return wrapper


def provide_d_sharing_connection(api):
    return make_sharing_connection_api_wrapper(api, ftype=FTYPE_DIR)


def provide_sharing_connection(api):
    return make_sharing_connection_api_wrapper(api, ftype=None)


def make_server_connection_api_wrapper(api, connect: bool):
    def wrapper(client: 'Client', args: Args, _1: Connection):
        # Wraps api providing the connection parameters.
        # The provided connection is the client current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if server connection exists before invoking %s", api.__name__)

        conn = client._get_current_server_connection_or_create_from_server_location_args(
            args,
            connect=connect
        )

        if not conn or not conn.is_established(): # always check socket level connection
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        if connect and not conn.is_connected_to_server(): # check application level connection
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Method call

        log.d("Server connection established, invoking '%s'", api.__name__)
        api(client, args, conn)

        # Cleanup

        if conn != client.connection:
            log.d("Destroying temporary server connection")

            if connect:
                conn.disconnect()
            else:
                log.d("Server connection doesn't need to be disconnect()ed since connect=False")
                conn.destroy_connection()
        # else: # we have used our current server connection; don't disconnect it

    return wrapper

def provide_server_connection(api):
    return make_server_connection_api_wrapper(api, connect=True)

def provide_connection(api):
    return make_server_connection_api_wrapper(api, connect=False)

# decorator
def require_unix(api):
    def require_unix_wrapper(client: 'Client', args: Args, conn: Connection):
        if not is_unix():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)
        return api(client, args, conn)
    return require_unix_wrapper

# ==================================================================

class CommandExecutionError(Exception):
    def __init__(self, errors: AnyErrs = ClientErrors.ERR_0):
        self.errors = errors

# class HandledKeyboardInterrupt(KeyboardInterrupt):
class HandledKeyboardInterrupt(Exception):
    pass


class OverwritePolicy:
    PROMPT = RequestsParams.PUT_NEXT_OVERWRITE_PROMPT
    YES = RequestsParams.PUT_NEXT_OVERWRITE_YES
    NO = RequestsParams.PUT_NEXT_OVERWRITE_NO
    NEWER = RequestsParams.PUT_NEXT_OVERWRITE_NEWER
    DIFF_SIZE = RequestsParams.PUT_NEXT_OVERWRITE_DIFF_SIZE
    NEWER_DIFF_SIZE = RequestsParams.PUT_NEXT_OVERWRITE_NEWER_DIFF_SIZE

    NEWERS = [NEWER, NEWER_DIFF_SIZE]
    DIFF_SIZES = [DIFF_SIZE, NEWER_DIFF_SIZE]



# ==================================================================

class Findings:
    def __init__(self, path: Union[str, Path], infos: List[FileInfo]):
        self.path: Union[str, Path] = path
        self.infos: List[FileInfo] = infos

    def __len__(self):
        return len(self.infos)

    def __getitem__(self, item):
        return self.infos[item]

class Finding:
    def __init__(self, path: Union[str, Path], info: FileInfo):
        self.path: Union[str, Path] = path
        self.info: FileInfo = info

# ==================================================================



class Client:
    FINDINGS_RE = re.compile(r"\$([a-zA-Z])(\d+):?(\d+)?")

    def __init__(self):
        self.connection: Optional[Connection] = None

        # letter => findings, pwd when find the was performed
        self._local_findings: Dict[str, Findings] = {}
        self._local_finding_letter: str = "a"

        # letter => findings, rpwd when find the was performed
        self._remote_findings: Dict[str, Findings] = {}
        self._remote_finding_letter: str = "A"

        def LOCAL(parser: ArgsSpec) -> ArgsSpec:
            return parser

        def SERVER(connectionful_parser: ArgsSpec, connectionless_parser: ArgsSpec) -> ArgsSpec:
            if self.is_connected_to_server():
                log.d("serverconnection_parser_provider -> 'already connect' parser")
                return connectionful_parser

            log.d("serverconnection_parser_provider -> 'not connect' parser")
            return connectionless_parser


        def SHARING(connectionful_parser: ArgsSpec, connectionless_parser: ArgsSpec) -> ArgsSpec:
            if self.is_connected_to_sharing():
                log.d("sharingconnection_parser_provider -> 'already connect' parser")
                return connectionful_parser

            log.d("sharingconnection_parser_provider -> 'not connect' parser")
            return connectionless_parser


        # connectionful, connectionless, executor
        self._command_dispatcher: Dict[
            str, Tuple[
                Callable[..., ArgsSpec],
                List[ArgsSpec],
                Callable[[Args, Optional[Connection]], None]
            ]
        ] = {

            Commands.LOCAL_CHANGE_DIRECTORY: (LOCAL, [Cd()], self.cd),
            Commands.LOCAL_STAT: (LOCAL, [Stat()], self.stat),
            Commands.LOCAL_LIST_DIRECTORY: (LOCAL, [Ls()], self.ls),
            Commands.LOCAL_TREE_DIRECTORY: (LOCAL, [Tree()], self.tree),
            Commands.LOCAL_FIND: (LOCAL, [Find()], self.find),
            Commands.LOCAL_DISK_USAGE: (LOCAL, [Du()], self.du),
            Commands.LOCAL_CREATE_DIRECTORY: (LOCAL, [Mkdir()], self.mkdir),
            Commands.LOCAL_CURRENT_DIRECTORY: (LOCAL, [Pwd()], self.pwd),
            Commands.LOCAL_REMOVE: (LOCAL, [Rm()], self.rm),
            Commands.LOCAL_MOVE: (LOCAL, [Mv()], self.mv),
            Commands.LOCAL_COPY: (LOCAL, [Cp()], self.cp),
            Commands.LOCAL_SHELL: (LOCAL, [Shell()], self.shell),

            Commands.REMOTE_CHANGE_DIRECTORY: (SHARING, [Rcd(0), Rcd(1)], self.rcd),
            Commands.REMOTE_STAT: (SHARING, [Rstat(1), Rstat(2)], self.rstat),
            Commands.REMOTE_LIST_DIRECTORY: (SHARING, [Rls(0), Rls(1)], self.rls),
            Commands.REMOTE_TREE_DIRECTORY: (SHARING, [Rtree(0), Rtree(1)], self.rtree),
            Commands.REMOTE_FIND: (SHARING, [Rfind(0), Rfind(1)], self.rfind),
            Commands.REMOTE_DISK_USAGE: (SHARING, [Rdu(0), Rdu(1)], self.rdu),
            Commands.REMOTE_CREATE_DIRECTORY: (SHARING, [Rmkdir(1), Rmkdir(2)], self.rmkdir),
            Commands.REMOTE_CURRENT_DIRECTORY: (SHARING, [Rpwd(0), Rpwd(1)], self.rpwd),
            Commands.REMOTE_REMOVE: (SHARING, [Rrm(1), Rrm(2)], self.rrm),
            Commands.REMOTE_MOVE: (SHARING, [Rmv(2), Rmv(3)], self.rmv),
            Commands.REMOTE_COPY: (SHARING, [Rcp(2), Rcp(3)], self.rcp),
            Commands.REMOTE_SHELL: (SERVER, [Rshell(0), Rshell(1)], self.rshell),

            Commands.GET: (SHARING, [Get(0), Get(1)], self.get),
            Commands.PUT: (SHARING, [Put(0), Put(1)], self.put),

            Commands.SCAN: (SERVER, [Scan(), Scan()], self.scan),
            Commands.LIST: (SERVER, [ListSharings(0), ListSharings(1)], self.list),
            Commands.INFO: (SERVER, [Info(0, 1), Info(1, 0)], self.info),

            Commands.CONNECT: (SERVER, [Connect(), Connect()], self.connect),
            Commands.DISCONNECT: (SERVER, [Disconnect(0), Disconnect(1)], self.disconnect),

            Commands.OPEN: (SERVER,[Open(), Open()], self.open),
            Commands.CLOSE: (SHARING, [Close(0), Close(1)], self.close),

            Commands.PING: (SERVER, [Ping(0), Ping(1)], self.ping),
        }

    def has_command(self, command: str) -> bool:
        return command in self._command_dispatcher

    # def execute_command(self, command: str, command_args: List[str]) -> AnyErr:
    def execute_command(self, command: str, command_suffix: str = "") -> AnyErrs:
        if not self.has_command(command):
            log.w(f"Unknown command: {command}")
            return ClientErrors.COMMAND_NOT_RECOGNIZED

        # command_args_copy = command_args.copy()
        # log.i("Executing %s(%s)", command, command_args_copy)
        log.i(f"Executing {command} {command_suffix}")

        # Check which parser to use
        # The local Commands and the connected remote Commands use
        # the same parsers, while the unconnected remote Commands
        # need one more leading parameter (the remote sharing location)
        parser_provider, parser_provider_args, executor = self._command_dispatcher[command]

        parser = parser_provider(*parser_provider_args)

        # Parse args using the parsed bound to the command
        try:
            args = parser.parse(command_suffix)
        except ArgsParseError as err:
            log.e("Command's arguments parse failed: %s", str(err))
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.i("Parsed command arguments\n%s", args)

        try:
            executor(args, None) # will be provided by decorators
            return ClientErrors.SUCCESS

        except HandledKeyboardInterrupt:
            return ClientErrors.SUCCESS

        except CommandExecutionError as ex:
            # "Expected" fail
            err = ex.errors if ex.errors else ClientErrors.COMMAND_EXECUTION_FAILED
            log.eexception("CommandExecutionError: %s", err)
            return err
        except ConnectionError as ex:
            err = os_error_str(ex) or ClientErrors.COMMAND_EXECUTION_FAILED
            log.eexception("ConnectionError: %s", err)
            return err
        except Exception as ex:
            # Every other unexpected fail: destroy connection
            log.eexception("Exception caught while executing command\n%s", ex)
            self.destroy_connection()
            return ClientErrors.COMMAND_EXECUTION_FAILED


    def is_connected_to_server(self) -> bool:
        return True if self.connection and \
                       self.connection.is_connected_to_server() else False

    def is_connected_to_sharing(self) -> bool:
        return True if self.connection and \
                       self.connection.is_connected_to_sharing() else False

    def destroy_connection(self, clean: bool = True, clear_findings: bool = True):
        """ Destroy an eventual established server connection (and thus sharing conn) """
        try:
            log.d("Destroying connection and invalidating it")
            if self.is_connected_to_server():
                self.connection.destroy_connection(clean=clean)
            # Server closes the sharing by itself
            # There's no need to close() the sharing connection
        except:
            log.w("Clean disconnection failed, invalidating connection anyway")

        if self.connection:
            # Clear findings only if 1) required) 2) the connection was up
            self.connection = None

            if clear_findings:
                self._clear_remote_findings()

    def renew_connection(self, clean: bool = True):
        log.i("Renewing connection")

        # Are we actually connected to a server (or a sharing)?
        if not self.is_connected_to_server():
            log.w("Cannot renew connection, not connected neither to server nor sharing")
            return

        # Build the current server location
        current_server_location = ServerLocation(
            name=self.connection.server_info.get("name"),
            ip=self.connection.server_ip(),
            port=self.connection.server_port()
        )

        # Build the current sharing location, if possible
        current_sharing_location = None

        if self.is_connected_to_sharing():
            current_sharing_location = SharingLocation(
                sharing_name=self.connection.current_sharing_name(),
                server_location=current_server_location,
                path=self.connection.current_rcwd()
            )

        # Destroy the current connection
        # Tries to keep the findings, if we are able to establish the
        # connection again successfully
        self.destroy_connection(clean=clean, clear_findings=False)

        # Perform a connect()[+ open()] again
        try:
            if current_sharing_location:
                log.d("Renewal: performing open() since was not connected to a sharing")
                self._open(current_sharing_location)
            else:
                log.d("Renewal: performing connect() only since was not connected to a sharing")
                self._connect(current_server_location)
        except Exception as ex:
            log.w(f"Failed to renew the connection: {ex}")
            # No reason to keep the findings, destroying those
            self._clear_remote_findings()

    # === LOCAL Commands ===

    def cd(self, args: Args, _):
        directory = self._local_path(args.get_positional(), default="~")
        log.i(">> CD %s", directory)

        if not directory.is_dir():
            raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS, directory))

        try:
            os.chdir(str(directory))
        except FileNotFoundError:
            raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                  q(directory)))
        except PermissionError:
            raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                  q(directory)))
        except OSError as oserr:
            raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                  os_error_str(oserr),
                                                  q(directory)))


    def pwd(self, _: Args, _2):
        log.i(">> PWD")

        print(Path.cwd())

    def stat(self, args: Args, _):
        def stat_provider(ps: List[str]):
            paths = []
            for p in ps:
                paths += self._local_paths(p)

            finfos = []
            for p in paths:
                try:
                    finfos.append(create_file_info_full(p, raise_exceptions=True))
                except FileNotFoundError:
                    raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                          q(p)))
                except PermissionError:
                    raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                          q(p)))
                except OSError as oserr:
                    raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                          os_error_str(oserr),
                                                          q(p)))

            return finfos

        self._xstat(args, stat_provider)

    def ls(self, args: Args, _):

        def ls_provider(path: str, **kwargs):
            p = self._local_path(path)
            kws = {k: v for k, v in kwargs.items() if k in
                   ["sort_by", "name", "reverse", "hidden", "details"]}
            try:
                ls_res = ls(p, **kws)
            except FileNotFoundError:
                raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                      q(p)))
            except PermissionError:
                raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                      q(p)))
            except OSError as oserr:
                raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                      os_error_str(oserr),
                                                      q(p)))

            return ls_res

        self._xls(args, ls_provider, "LS")

    def tree(self, args: Args, _):

        def tree_provider(path, **kwargs):
            p = self._local_path(path)
            kws = {k: v for k, v in kwargs.items() if k in
                   ["sort_by", "name", "reverse", "max_depth", "hidden", "details"]}
            try:
                tree_res = tree(p, **kws)
            except FileNotFoundError:
                raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                      q(p)))
            except PermissionError:
                raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                      q(p)))
            except OSError as oserr:
                raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                      os_error_str(oserr),
                                                      q(p)))

            return tree_res

        self._xtree(args, tree_provider, "TREE")

    def find(self, args: Args, _):

        def find_provider(path: str, **kwargs):
            p = self._local_path(path)
            kws = {k: v for k, v in kwargs.items() if k in
                   ["name", "regex", "ftype", "case_sensitive", "details", "max_depth"]}
            try:
                find_res = find(p, **kws)
            except FileNotFoundError:
                raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                      q(p)))
            except PermissionError:
                raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                      q(p)))
            except OSError as oserr:
                raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                      os_error_str(oserr),
                                                      q(p)))

            return find_res

        self._xfind(args, find_provider, "FIND", findings_adder=self._add_local_findings)

    def du(self, args: Args, _):
        path = self._local_path(args.get_positional())
        human = Du.HUMAN in args

        if not path.exists():
            raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS, path))

        log.i(">> DU %s", path)

        try:
            usage = du(path)
            usage_size = size_str(usage) if human else usage

            print(f"{usage_size} {str(path.resolve())}")
        except FileNotFoundError:
            raise CommandExecutionError(errno_str(ClientErrors.NOT_EXISTS,
                                                  q(path)))
        except PermissionError:
            raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                  q(path)))
        except OSError as oserr:
            raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                  os_error_str(oserr),
                                                  q(path)))


    def mkdir(self, args: Args, _):
        directory = self._local_path(args.get_positional())

        if not directory:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        directory = Path(directory)

        log.i(">> MKDIR %s", directory)

        try:
            directory.mkdir(parents=True)
        except PermissionError:
            raise CommandExecutionError(errno_str(ClientErrors.PERMISSION_DENIED,
                                                  q(directory)))
        except FileExistsError:
            raise CommandExecutionError(errno_str(ClientErrors.DIRECTORY_ALREADY_EXISTS,
                                                  q(directory)))
        except OSError as oserr:
            raise CommandExecutionError(errno_str(ClientErrors.ERR_2,
                                                  os_error_str(oserr),
                                                  q(directory)))

    def rm(self, args: Args, _):
        paths = []
        for p in args.get_positionals():
            paths += self._local_paths(p)

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RM %s", paths)

        errors = []

        for p in paths:
            err = self._rm(p)
            if err:
                errors.append(err)

        if errors:
            raise CommandExecutionError(errors)


    def mv(self, args: Args, _):
        errors = []

        def handle_mv_error(exc: Exception, src: Path, dst: Path):
            if isinstance(exc, PermissionError):
                errors.append(errno_str(ClientErrors.MV_PERMISSION_DENIED,
                                        q(src), q(dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(errno_str(ClientErrors.MV_NOT_EXISTS,
                                        q(src), q(dst)))
            if isinstance(exc, OSError):
                print(exc)
                errors.append(errno_str(ClientErrors.MV_OTHER_ERROR,
                                        os_error_str(exc), q(src), q(dst)))
            else:
                errors.append(errno_str(ClientErrors.MV_OTHER_ERROR,
                                    exc, q(src),
                                    q(dst)))

        self._mvcp(args, mv, "MV", error_callback=handle_mv_error)

        if errors:
            raise CommandExecutionError(errors)

    def cp(self, args: Args, _):

        errors = []

        def handle_cp_error(exc: Exception, src: Path, dst: Path):
            if isinstance(exc, PermissionError):
                errors.append(errno_str(ClientErrors.CP_PERMISSION_DENIED,
                                        q(src), q(dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(errno_str(ClientErrors.CP_NOT_EXISTS,
                                        q(src), q(dst)))
            elif isinstance(exc, OSError):
                errors.append(errno_str(ClientErrors.CP_OTHER_ERROR,
                                        os_error_str(exc), q(src), q(dst)))
            else:
                errors.append(errno_str(ClientErrors.CP_OTHER_ERROR,
                                        exc, q(src), q(dst)))

        self._mvcp(args, cp, "CP", error_callback=handle_cp_error)

        if errors:
            raise CommandExecutionError(errors)

    @classmethod
    def shell(cls, args: Args, _):
        if not is_unix():
            log.w("shell not supported on this platform")
            raise CommandExecutionError(ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX)

        shell_cmd = args.get_unparsed_arg()

        if not shell_cmd:
            passwd: struct_passwd = user()
            log.i(f"{passwd.pw_uid} {passwd.pw_name} - shell: {passwd.pw_shell}")
            shell_cmd = passwd.pw_shell

        log.i(">> SHELL %s", shell_cmd)
        retcode = pty_attached(shell_cmd)
        if retcode != 0:
            log.w("Command return code = %d", retcode)


    # =================================================
    # ================ SERVER Commands ================
    # =================================================


    def connect(self, args: Args, _,):
        log.i(">> CONNECT")

        server_location = ServerLocation.parse(args.get_positional())

        if not server_location:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        self._connect(server_location)


    @provide_server_connection
    def disconnect(self, args: Args, conn: Connection):
        log.i(">> DISCONNECT")
        conn.disconnect()


    def open(self, args: Args, _):
        log.i(">> OPEN")

        sharing_location = SharingLocation.parse(args.get_positional())

        if not sharing_location:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        self._open(sharing_location)

    @provide_server_connection
    @require_unix
    def rshell(self, args: Args, conn: Connection):
        rshell_cmd = args.get_unparsed_arg()

        termsize = terminal_size()
        log.i(f">> RSHELL {rshell_cmd} (size={termsize})", )

        rshell_resp = conn.rshell(rshell_cmd, cols=termsize[0], rows=termsize[1])
        ensure_success_response(rshell_resp)
        retcode = None

        # --- STDOUT/STDERR RECEIVER ---

        def rshell_out_receiver():
            nonlocal retcode

            try:
                while retcode is None:
                    in_b = conn.read(trace=True)

                    event_type: int = in_b[0]
                    log.d("Event type = %d", event_type)

                    if event_type == RexecEventType.DATA:
                        data_b = in_b[1:]
                        log.d("RSHELL recv: %s", repr(data_b))

                        try:
                            sys.stdout.buffer.write(data_b)
                            sys.stdout.buffer.flush()
                        except OSError as oserr:
                            # EWOULDBLOCK may arise something...
                            log.w("Ignoring OSerror: %s", str(oserr))
                    elif event_type == RexecEventType.EOF:
                        log.d("EOF from remote")
                    elif event_type == RexecEventType.RETCODE:
                        log.d("Remote process finished")
                        retcode = btoi(in_b[1:])
                    else:
                        log.w("Can't handle event of type %d", event_type)

                log.i("RSHELL done (%d)", retcode)
                # print()
            except Exception:
                log.eexception("Unexpected error occurred on rshell out receiver thread")
                retcode = -1


        rshell_out_receiver_th = threading.Thread(
            target=rshell_out_receiver, daemon=True)
        rshell_out_receiver_th.start()

        # --- STDIN SENDER ---

        # Put stdin in raw mode (read char by char) [taken from pty.spawn]
        tty_mode = None
        try:
            tty_mode = tty.tcgetattr(STDIN)
            tty.setraw(STDIN)
        except tty.error:
            log.w("Failed to setraw() mode")

        try:
            while retcode is None:
                try:
                    # Do not block so that we can exit when the process finishes
                    # Sleep for a little between each select call
                    rlist, wlist, xlist = select.select([pty.STDIN_FILENO], [], [], 0.04)

                    if pty.STDIN_FILENO in rlist:
                        data_b = os.read(STDIN, 1024)

                        if not data_b:
                            log.d("Sending EOF")
                            out_b = RexecEventType.EOF_B
                        else:
                            log.d("Sending data: %s", repr(data_b))
                            out_b = RexecEventType.DATA_B + data_b

                        conn.write(out_b, trace=True)

                except KeyboardInterrupt:
                    log.d("rexec CTRL+C")
                    conn.write(RexecEventType.KILL_B, trace=True)

        except OSError:
            log.eexception("OSError")
        finally:
            # Restore stdin in blocking mode [taken from pty.spawn]
            try:
                if tty_mode:
                    tty.tcsetattr(STDIN, tty.TCSAFLUSH, tty_mode)
            except tty.error:
                log.w("Failed to restore tty_mode mode")

        # Wait everybody
        rshell_out_receiver_th.join()

        # Stop the remote stdin receiver by sending a ENDACK
        log.d("Sending ENDACK to remote")
        conn.write(RexecEventType.ENDACK_B, trace=True)

    @provide_connection
    def ping(self, args: Args, conn: Connection):
        count = args.get_option_param(Ping.COUNT, default=None)

        i = 1
        while not count or i <= count:
            timer = Timer(start=True)
            resp = conn.ping()
            timer.stop()

            if is_data_response(resp) and resp.get("data") == "pong":
                print("[{}] PONG from {}  |  time={:.1f}ms".format(
                    i,
                    server_info_short_str(conn.server_info),
                    timer.elapsed_ms())
                )
            else:
                print(f"[{i}] FAIL")

            i += 1
            time.sleep(1)

    # =================================================
    # =============== PROBING Commands ================
    # =================================================

    def scan(self, args: Args, _):
        show_sharings_details = Scan.SHOW_SHARINGS_DETAILS in args
        show_all_details = Scan.SHOW_ALL_DETAILS in args

        log.i(">> SCAN")

        servers_found = 0
        SEP = "========================================"

        def response_handler(client: Endpoint,
                             server_info_full: ServerInfoFull) -> bool:
            nonlocal servers_found

            log.i("Handling DISCOVER response from %s\n%s", str(client), str(server_info_full))
            # Print as soon as they come

            s = ""

            if not servers_found:
                log.i("======================")
            # else:
            #     s += "\n"

            s += bold("{}. {}".format(
                      servers_found + 1,
                      server_info_short_str(server_info_full)))

            if show_all_details:
                s += "\n" + server_pretty_str(server_info_full) + "\n" + SEP
            else:
                sharings_str = sharings_pretty_str(
                    server_info_full.get("sharings"),
                    details=show_sharings_details,
                    indent=2)

                if sharings_str:
                    # s +=  "\n" + sharings_str
                    s +=  "\n" + sharings_str
                # else: NONE

            # DELETE_EOL for overwrite progress bar render

            print(ansi.RESET_LINE + s, flush=True)

            servers_found += 1

            return True     # Continue DISCOVER

        self._discover(
            response_handler=response_handler,
            progress=True,
            success_if_ends=True
        )

        log.i("======================")

    @provide_connection
    def info(self, _: Args, conn: Connection):
        highlights = [s for s in conn.server_info.get("sharings")
                      if s.get("name") == conn.current_sharing_name()]
        print(server_pretty_str(conn.server_info, highlight_sharings=highlights))


    @provide_connection
    def list(self, _: Args, conn: Connection):
        log.i(">> LIST")

        resp = conn.list()
        ensure_data_response(resp)

        sharings_str = sharings_pretty_str(resp.get("data"),
                                           details=True)

        if sharings_str:
            print(sharings_str)
        else:
            log.w("Remote server doesn't have any sharing")


    # =================================================
    # ================ SHARING Commands ===============
    # =================================================

    @provide_d_sharing_connection
    def close(self, args: Args, conn: Connection):
        log.i(">> CLOSE")
        conn.close()

        # noinspection PyUnresolvedReferences
        if conn and conn.is_connected_to_server() and \
                getattr(conn, "created_with_open", False):
            log.d("Closing server connection too since opened due open")
            conn.disconnect()

        self._clear_remote_findings()


    @provide_d_sharing_connection
    def rpwd(self, args: Args, conn: Connection):
        log.i(">> RPWD")
        resp = conn.rpwd()
        ensure_data_response(resp)

        rcwd = resp.get("data")

        print(rcwd)

    @provide_d_sharing_connection
    def rcd(self, args: Args, conn: Connection):
        directory = self._remote_path(args.get_positional(default="/"))

        log.i(">> RCD %s", directory)

        resp = conn.rcd(directory)
        ensure_data_response(resp)

        log.d("Current rcwd: %s", conn.current_rcwd())

    @provide_sharing_connection
    def rstat(self, args: Args, conn: Connection):
        def rstat_provider(paths: List[str]):
            resp = conn.rstat(paths)
            data_dict = ensure_data_response(resp)
            return data_dict.values()

        self._xstat(args, data_provider=rstat_provider)


    @provide_sharing_connection
    def rls(self, args: Args, conn: Connection):
        def rls_provider(f, **kwargs):
            resp = conn.rls(**kwargs, path=self._remote_path(f))
            return ensure_data_response(resp)

        self._xls(args, data_provider=rls_provider, data_provider_name="RLS")

    @provide_d_sharing_connection
    def rtree(self, args: Args, conn: Connection):
        def rtree_provider(f, **kwargs):
            resp = conn.rtree(**kwargs, path=self._remote_path(f))
            return ensure_data_response(resp)

        self._xtree(args, data_provider=rtree_provider, data_provider_name="RTREE")

    @provide_sharing_connection
    def rfind(self, args: Args, conn: Connection):
        def rfind_provider(f, **kwargs):
            resp = conn.rfind(**kwargs, path=self._remote_path(f))
            return ensure_data_response(resp)

        # Add findings only for an established connection (not temporary one)
        findings_adder = self._add_remote_findings if conn == self.connection else None
        self._xfind(args, rfind_provider, "RFIND", findings_adder=findings_adder)

    @provide_sharing_connection
    def rdu(self, args: Args, conn: Connection):
        path = self._remote_path(args.get_positional())
        human = Du.HUMAN in args

        log.i(">> RDU %s", path)

        resp = conn.rdu(path=path)
        resp_data = ensure_data_response(resp)

        for usage in resp_data:
            usage_size = size_str(usage[1]) if human else usage[1]
            usage_file = usage[0]
            print(f"{usage_size} {usage_file}")


    @provide_d_sharing_connection
    def rmkdir(self, args: Args, conn: Connection):
        directory = self._remote_path(args.get_positional())

        if not directory:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RMKDIR %s", directory)

        resp = conn.rmkdir(directory)
        ensure_success_response(resp)

    @provide_d_sharing_connection
    def rrm(self, args: Args, conn: Connection):
        paths = []
        for p in args.get_positionals():
            paths += self._remote_paths(p)

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RRM %s ", paths)

        resp = conn.rrm(paths)
        ensure_success_response(resp)

    @provide_d_sharing_connection
    def rmv(self, args: Args, conn: Connection):
        self._rmvcp(args, api=conn.rmv, api_name="RMV")

    @provide_d_sharing_connection
    def rcp(self, args: Args, conn: Connection):
        self._rmvcp(args, api=conn.rcp, api_name="RCP")

    @provide_sharing_connection
    def get(self, args: Args, conn: Connection):
        try:
            self._get(args, conn)
        except KeyboardInterrupt:
            # Renew (close and reopen) the connection if CTRL + C is detected
            # during the transfer.
            # We can't do any better since we only use a socket, and not
            # We can't do any better since we only use a socket, and not
            # a control one like FTP.
            # Renew not in a clean manner: we can't send/receive any message in
            # this moment since we are in the middle of a transfer, just shutdown
            # the socket.
            log.w("CTRL+C detected while transferring - renewing connection")
            self.renew_connection(clean=False)


    @provide_sharing_connection
    def put(self, args: Args, conn: Connection):
        try:
            self._put(args, conn)
        except KeyboardInterrupt:
            # Renew (close and reopen) the connection if CTRL + C is detected
            # during the transfer.
            # We can't do any better since we only use a socket, and not
            # a control one like FTP.
            # Renew not in a clean manner: we can't send/receive any message in
            # this moment since we are in the middle of a transfer, just shutdown
            # the socket.
            log.w("CTRL+C detected while transferring - renewing connection")
            self.renew_connection(clean=False)

    def _get(self, args: Args, conn: Connection):
        # Compute remote paths (replacing findings)
        files = []
        for p in args.get_positionals():
            files += self._remote_paths(p)
        log.i(f"Remote files to GET\n{j(files)}")

        # Args parsing
        dest = args.get_option_param(Get.DESTINATION)

        if dest:
            dest = Path(dest)
            dest_ftype = ftype_of(dest)

        do_check = Get.CHECK in args
        quiet = Get.QUIET in args
        no_hidden = Get.NO_HIDDEN in args
        sync = Get.SYNC in args
        preview = Get.PREVIEW in args
        preview_total_size = 0

        chunk_size = args.get_option_param(Get.CHUNK_SIZE)
        use_mmap = args.get_option_param(Get.MMAP)

        transfer_socket = conn._stream._socket

        # Overwrite preference
        if [Get.OVERWRITE_YES in args, Get.OVERWRITE_NO in args,
            True if (Get.OVERWRITE_NEWER in args or Get.OVERWRITE_DIFF_SIZE in args) else False,
            Get.SYNC in args].count(True) > 1:
            log.e("Only one between -n, -y, -s and (-N and/or -S) can be specified")
            raise CommandExecutionError("Only one between -n, -y, -s and (-N and/or -S) can be specified")

        overwrite_policy = OverwritePolicy.PROMPT

        if Get.OVERWRITE_YES in args: # -y
            overwrite_policy = OverwritePolicy.YES
        elif Get.OVERWRITE_NO in args: # -n
            overwrite_policy = OverwritePolicy.NO
        elif Get.OVERWRITE_NEWER in args and Get.OVERWRITE_DIFF_SIZE in args: # -NS
            overwrite_policy = OverwritePolicy.NEWER_DIFF_SIZE
        elif Get.OVERWRITE_NEWER in args: # -N
            overwrite_policy = OverwritePolicy.NEWER
        elif Get.OVERWRITE_DIFF_SIZE in args: # -S
            overwrite_policy = OverwritePolicy.DIFF_SIZE
        elif Get.SYNC in args: # -s
            # Sync is the same as -NS but deletes the old files after the transfer
            overwrite_policy = OverwritePolicy.NEWER_DIFF_SIZE

        log.i(f"Overwrite policy: {overwrite_policy}")

        # Stats
        progressor = None
        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Errors
        errors = []
        outcome_resp = None

        # If sync is True track the files in the current directory
        # so that we can remove old files (the one for which no file info
        # is retrieved from the server) after the transfer completes.
        sync_table = None

        def compute_sync_table():
            nonlocal sync_table

            sync_path = dest or Path.cwd()
            log.d(f"Computing sync table over: {sync_path}")

            sync_table_entries = []

            def add_path_to_sync_table(p):
                nonlocal sync_table_entries
                log.d(f"Adding '{p}' hierarchy to SYNC table")
                # Preserve order for perform RM in optimal order (parents first)
                findings = find(p)
                if findings:
                    sync_table_entries += findings

            if files:
                for file in files:
                    sync_path_trail = Path(file).parts[-1]
                    add_path_to_sync_table(sync_path / sync_path_trail)
            else:
                # No path specified, will get the content wrapped into
                # a folder with the rcwd name
                sync_path_trail = conn.current_rcwd()
                if not sync_path_trail or sync_path_trail == "/":
                    # No rcwd? we will get the content wrapped into a folder
                    # with the sharing name
                    sync_path_trail = conn.current_sharing_name()
                add_path_to_sync_table(sync_path / sync_path_trail)

            sync_table = OrderedDict({entry.get("name"): None for entry in sync_table_entries})
            log.d(f"SYNC table computed ({len(sync_table_entries)})\n" +
                  "\n".join(sync_table.keys()))

        def compute_dest_path(finfo_: FileInfo):
            """
            --dest handling

            |   alias       |    SRC    |    DEST    |   ACTION
            --------------------------------------------------------------
                1_file2none      file        ----        write file
                1_file2file      file        file        overwrite file
                1_file2dir       file        dir         put file into dir
                1_dir2none       dir         ----        write dir
                1_dir2file       dir         file        ERROR
                1_dir2dir        dir         dir         put dir into dir

                2_any2none       any         ----        ERROR
                2_any2file       any         file        ERROR
                2_any2dir        any         dir         put files/dirs into dir
            """
            fname_ = Path(finfo_.get("name"))

            if not dest:
                return fname_

            multiple_ = len(files) > 1

            source_ftype = "any"
            if not multiple_:
                source_ftype = FTYPE_DIR if len(fname_.parts) > 1 else finfo_.get("ftype")

            log.d(f"Handling destpath for case "
                  f"{(2 if multiple_ else 1)}_{source_ftype or 'any'}2{dest_ftype or 'none'}")

            if not multiple_:
                if source_ftype == FTYPE_FILE:
                    if not dest_ftype:
                        # 1_file2none -> write file
                        output = dest
                    elif dest_ftype == FTYPE_FILE:
                        # 1_file2file -> overwrite file
                        output = dest
                    elif dest_ftype == FTYPE_DIR:
                        # 1_file2dir -> put file into dir
                        output = dest / fname_
                    else: # WTF
                        raise CommandExecutionError("Invalid --dest semantic")
                elif source_ftype == FTYPE_DIR:
                    if not dest_ftype:
                        # 1_dir2none -> replace dir name
                        output = dest / Path(*(fname_.parts[1:]))
                    elif dest_ftype == FTYPE_FILE:
                        # 1_dir2file -> ERROR
                        raise CommandExecutionError("Invalid --dest semantic: destination must be a directory")
                    elif dest_ftype == FTYPE_DIR:
                        # 1_dir2dir
                        output = dest / fname_
                    else: # WTF
                        raise CommandExecutionError("Invalid --dest semantic")
                else:
                    raise CommandExecutionError("Invalid --dest semantic")
            else:
                if dest_ftype == FTYPE_FILE:
                    # 2_any2file (ok)
                    raise CommandExecutionError("Invalid --dest semantic: destination must be a directory")
                elif dest_ftype == FTYPE_DIR:
                    # 2_any2dir (ok)
                    output = dest / fname_
                else:
                    # 2_any2none (ok)
                    raise CommandExecutionError("Invalid --dest semantic: destination must exists")

            return output

        # Actual GET request is here
        resp = conn.get(files,
                        check=do_check, no_hidden=no_hidden,
                        mmap=use_mmap, chunk_size=chunk_size)
        ensure_success_response(resp)

        while True:
            # The first next() fetch never implies a new file to be put
            # on the transfer socket.
            # We have to check whether we want to eventually overwrite
            # the file, and then tell the server next() if
            # 1. Really transfer the file
            # 2. Skip the file

            # If OverwritePolicy.YES transfer immediately since we won't
            # ask to the user whether overwrite or not.
            # The only exception is if preview is True, in that case we won't
            # perform the transfer so do a regular seek

            if overwrite_policy == OverwritePolicy.YES and not preview:
                action = RequestsParams.GET_NEXT_ACTION_TRANSFER
            else:
                action = RequestsParams.GET_NEXT_ACTION_SEEK

            log.i(f"Sending '{action}' message")

            get_next_resp = conn.call({
                RequestsParams.GET_NEXT_ACTION: action
            })

            ensure_success_response(get_next_resp)
            data = get_next_resp.get("data")

            finfo: Optional[FileInfo] = None

            if data:
                finfo = data.get(ResponsesParams.GET_NEXT_FILE)

            if not finfo:
                log.i("Nothing more to GET")
                if data and data.get(ResponsesParams.GET_OUTCOME) is not None:
                    outcome_resp = get_next_resp
                break

            fname = finfo.get("name")
            fsize = finfo.get("size")
            ftype = finfo.get("ftype")
            fmtime = finfo.get("mtime")

            log.d(f"NEXT: '{fname}' [{ftype}]")

            local_path = compute_dest_path(finfo)

            log.d(f"Computed local path: {local_path}")

            # TODO
            if sync:
                if sync_table is None:
                    compute_sync_table()

                # Remove from the SYNC table eventually
                # Do the removal for each possible path within local_path
                # (so that we won't delete parent folder if the change is
                # inside the children)
                incremental_path = Path.cwd()
                for part in local_path.parts:
                    incremental_path = incremental_path / part
                    incremental_path_str = str(incremental_path)
                    log.d(f"Removing from SYNC table: '{incremental_path_str}'")
                    sync_table.pop(incremental_path_str, None)

            """
            Write/Overwrite policy
            
            |   alias       |    SRC    |    DEST    |   ACTION
            --------------------------------------------------------------
                file2none      file        ----        write file
                file2file      file        file        overwrite file (eventually)
                file2dir       file        dir         ERROR (skip)
                dir2none       dir         ----        create dir
                dir2file       dir         file        ERROR (skip)
                dir2dir        dir         dir         no-op
            """

            log.d(f"Handling GET case: "
                  f"{ftype}2{ftype_of(local_path)}")

            # Case: DIR
            if ftype == FTYPE_DIR:
                if not local_path.exists():
                    # dir2none => create dir
                    if not preview:
                        log.i(f"Creating directory {fname}")
                        try:
                            local_path.mkdir(parents=True, exist_ok=True)
                        except:
                            log.eexception("Failed to create parent directories; "
                                           "probably won't be able to write file")
                            # TODO
                            # A more clean way would be tell the server that
                            # we won't be able to receive any file children
                            # of this one, but for now we will skip when we fail
                    else:
                        print(green(f"+ [{size_str_justify(0)}] {local_path}"))
                elif local_path.is_file():
                    # dir2file => ERROR
                    log.w(f"Tried to get a DIR while local FILE exists with the name: {local_path}")
                # else
                #   dir2dir => no-op

                continue  # No FTYPE_FILE => neither skip nor transfer for next()

            if ftype != FTYPE_FILE:
                log.w(f"Cannot handle this ftype: {ftype}")
                continue  # No FTYPE_FILE => neither skip nor transfer for next()

            # Case: FILE
            local_path_parent = local_path.parent

            if action == RequestsParams.GET_NEXT_ACTION_SEEK:
                def skip_transfer():
                    ensure_success_response(conn.call({
                        RequestsParams.GET_NEXT_ACTION: RequestsParams.GET_NEXT_ACTION_SKIP
                    }))

                if local_path_parent:
                    if not preview:
                        log.i(f"Creating parent directories {local_path_parent}")
                        try:
                            local_path_parent.mkdir(parents=True, exist_ok=True)
                        except:
                            log.eexception("Failed to create parent directories; "
                                           "probably won't be able to write file")
                            skip_transfer()
                            # TODO
                            # A more clean way would be tell the server that
                            # we won't be able to receive any file children
                            # of this one, but for now we will skip when we fail
                            continue

                # Check whether the file already exists (and ensure is a file, if exists)

                if local_path.is_dir():
                    # file2dir => ERROR
                    log.w(f"Tried to get a FILE while local DIR exists with the name: {local_path}")
                    skip_transfer()
                    continue

                if local_path.is_file():
                    # file2file => overwrite (eventually)
                    log.w("File already exists, asking whether overwrite it (if needed)")

                    local_stat = local_path.stat()

                    # Overwrite handling

                    timer.stop() # Don't take the user time into account
                    current_overwrite_decision, overwrite_policy = self._ask_overwrite(
                        local_info=create_file_info(local_path, fstat=local_stat),
                        remote_info=finfo,
                        current_policy=overwrite_policy
                    )
                    timer.start()

                    log.d(f"Overwrite decision: {current_overwrite_decision}")

                    will_accept = False

                    if current_overwrite_decision == OverwritePolicy.YES:
                        will_accept = True
                    elif current_overwrite_decision in OverwritePolicy.NEWERS or \
                        current_overwrite_decision in OverwritePolicy.DIFF_SIZES:

                        if current_overwrite_decision in OverwritePolicy.NEWERS:
                            log.d(f"Checking whether skip based on mtime ({local_stat.st_mtime_ns} vs {fmtime})")
                            will_accept = will_accept or local_stat.st_mtime_ns < fmtime

                        if current_overwrite_decision in OverwritePolicy.DIFF_SIZES:
                            log.d(f"Checking whether skip based on size ({local_stat.st_size} vs {fsize})")
                            will_accept = will_accept or local_stat.st_size != fsize


                    if not will_accept:
                        # We must not overwrite the file due to overwrite policy
                        log.d(f"Would have seek, have to tell server to skip {fname}")
                        skip_transfer()
                        continue

                if preview:
                    # Don't transfer since it's only a preview
                    print(green(f"+ [{size_str_justify(fsize)}] {local_path}"))
                    preview_total_size += fsize
                    skip_transfer()
                    continue

                #

                # Regular case, we did a seek and now tell the server to transfer
                log.d(f"Would have seek, have to tell server to transfer {fname}")

                get_next_resp = conn.call({
                    RequestsParams.GET_NEXT_ACTION: RequestsParams.GET_NEXT_ACTION_TRANSFER
                })

                # The server may say the transfer can't be done actually (e.g. EPERM)
                if is_success_response(get_next_resp):
                    log.d("Transfer can actually begin")
                elif is_error_response(get_next_resp):
                    log.w("Transfer cannot be initialized due to remote error")

                    errors += get_next_resp.get("errors")

                    # All the errors will be reported at the end
                    continue
                else:
                    raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

            # else: file already put into the transfer socket

            # At this point the server is sending us the file
            if not quiet:
                progressor = FileProgressor(
                    fsize,
                    description="GET " + fname,
                    color_progress=PROGRESS_COLOR,
                    color_success=SUCCESS_COLOR,
                    color_error=ERROR_COLOR
                )

            log.i(f"Will write {local_path}")
            f = local_path.open("wb")

            cur_pos = 0
            expected_crc = 0

            while cur_pos < fsize:
                # Receive next chunk
                recv_size = min(chunk_size or BEST_BUFFER_SIZE, fsize - cur_pos)
                log.h("Waiting chunk...")

                chunk = transfer_socket.recv(recv_size)

                if not chunk:
                    log.i("END OF FILE")
                    raise CommandExecutionError()

                chunk_len = len(chunk)

                log.h(f"Received chunk of {chunk_len}B")
                # Write next chunk
                written_chunk_len = f.write(chunk)

                if chunk_len != written_chunk_len:
                    log.e("Written less bytes than expected; file will probably be corrupted")
                    return # Really don't know how to recover from this disaster

                cur_pos += chunk_len
                tot_bytes += chunk_len

                if do_check:
                    # Eventually update the CRC
                    expected_crc = zlib.crc32(chunk, expected_crc)

                if not quiet:
                    progressor.update(cur_pos)


            log.i(f"DONE {fname}")
            log.d(f"- crc = {expected_crc}")

            f.close()

            # Adjust the mtime based on the remote
            log.d(f"Setting mtime = {fmtime}")
            set_mtime(local_path, fmtime)

            # Eventually do CRC check
            if do_check:
                # CRC check on the received bytes
                crc = btoi(transfer_socket.recv(4))
                if expected_crc != crc:
                    log.e(f"Wrong CRC; transfer failed. expected={expected_crc} | written={crc}")
                    return # Really don't know how to recover from this disaster
                else:
                    log.d("CRC check: OK")

                # Length check on the written file
                written_size = local_path.stat().st_size
                if written_size != fsize:
                    log.e(f"File length mismatch; transfer failed. expected={fsize} ; written={written_size}")
                    return # Really don't know how to recover from this disaster
                else:
                    log.d("File length check: OK")

            n_files += 1
            if not quiet:
                progressor.success()

        # Wait for completion
        if not outcome_resp:
            outcome_resp = conn.read_json()
            ensure_data_response(outcome_resp, ResponsesParams.GET_OUTCOME)

        timer.stop()
        elapsed_s = timer.elapsed_s()

        # transfer_socket.close() # no since in-band

        # Take outcome and (eventually) errors out of the resp
        outcome = outcome_resp.get("data").get(ResponsesParams.GET_OUTCOME)
        outcome_errors = outcome_resp.get("data").get(ResponsesParams.GET_ERRORS)

        if outcome_errors:
            log.w("Response has errors")
            errors += outcome_errors

        sync_rm_ok = []
        sync_rm_errs = []

        if sync:
            # Check if there are old files to removes
            log.i(f"Will do {len(sync_table)} removal due to sync")

            # We can avoid some rm if we are deleting a parent folder
            # and sync_table contains the children.
            # Since the entries are sorted (walk_preoreder) we can iterate and skip
            # consecutive entries if they have the same prefix as the one before

            cur_del_path_str = None
            for path_str in sync_table.keys():
                if cur_del_path_str and path_str.startswith(cur_del_path_str):
                    log.d(f"Should remove '{path_str}' but skipping, already deleting parent")
                    continue
                # We actually have to delete this
                log.i(f"Will remove '{path_str}'")

                if preview:
                    print(red(f"- {path_str}"))
                else:
                    # regular case
                    err = self._rm(Path(path_str))
                    if not err:
                        # Removal OK
                        sync_rm_ok.append(path_str)
                    else:
                        sync_rm_errs.append(err)

                    cur_del_path_str = path_str

        log.i(f"GET outcome: {outcome}")

        if preview:
            print(f"Download size: {size_str(preview_total_size)}")
            return # Nothing else to do

        if n_files > 0:
            print("")
        print(f"GET outcome:  {outcome_str(outcome)}")
        print("-----------------------")
        print(f"Downloads:    {n_files} ({size_str(tot_bytes)})")
        print(f"Time:         {duration_str_human(round(elapsed_s))}")
        print(f"Avg. speed:   {speed_str(tot_bytes / elapsed_s)}")

        # Any error? (e.g. permission denied)
        if errors:
            print("-----------------------")
            print(f"GET errors:   {len(errors)}")
            for idx, err in enumerate(errors):
                err_str = formatted_error_from_error_of_response(err)
                print(f"{idx + 1}. {err_str}")

        # SYNC stats
        if sync:
            print("=======================")
            print(f"SYNC removed: {len(sync_rm_ok)}")
            for idx, removed in enumerate(sync_rm_ok):
                print(f"{idx + 1}. {removed}")

            if sync_rm_errs:
                print("-----------------------")
                print(f"SYNC errors:  {len(sync_rm_errs)}")
                for idx, err in enumerate(sync_rm_errs):
                    print(f"{idx + 1}. {err}")


    def _put(self, args: Args, conn: Connection):
        # Compute local paths (replacing findings)
        files = []
        for p in args.get_positionals():
            files += self._local_paths(p)

        sendfiles: Deque[Tuple[Path, Path]] = deque([])

        if len(files) == 0:
            files = [Path(".")]

        # Args parsing
        dest = args.get_option_param(Get.DESTINATION)
        do_check = Put.CHECK in args
        quiet = Put.QUIET in args
        no_hidden = Put.NO_HIDDEN in args
        sync = Put.SYNC in args
        preview = Put.PREVIEW in args
        preview_total_size = 0

        chunk_size = args.get_option_param(Put.CHUNK_SIZE, BEST_BUFFER_SIZE)
        use_mmap = args.get_option_param(Put.MMAP)

        transfer_socket = conn._stream._socket

        # Overwrite preference
        if [Put.OVERWRITE_YES in args, Put.OVERWRITE_NO in args,
            True if (Put.OVERWRITE_NEWER in args or Put.OVERWRITE_DIFF_SIZE in args) else False,
            Put.SYNC in args].count(True) > 1:
            log.e("Only one between -n, -y, -s and (-N and/or -S) can be specified")
            raise CommandExecutionError("Only one between -n, -y, -s and (-N and/or -S) can be specified")

        overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_PROMPT

        if Put.OVERWRITE_YES in args:
            overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_YES
        elif Put.OVERWRITE_NO in args:
            overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_NO
        elif Put.OVERWRITE_NEWER in args and Put.OVERWRITE_DIFF_SIZE in args:
            overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_NEWER_DIFF_SIZE
        elif Put.OVERWRITE_NEWER in args:
            overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_NEWER
        elif Put.OVERWRITE_DIFF_SIZE in args:
            overwrite_policy = RequestsParams.PUT_NEXT_OVERWRITE_DIFF_SIZE
        elif Put.SYNC in args:
            # Sync is the same as -NS but deletes the old files after the transfer
            overwrite_policy = OverwritePolicy.NEWER_DIFF_SIZE

        log.i(f"Overwrite policy: {overwrite_policy}")

        # Stats
        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Errors
        errors = []

        resp = conn.put(check=do_check, sync=sync, preview=preview,
                        dest=dest, is_multiple= True if len(files) > 1 else False)
        ensure_success_response(resp)


        for p in files:
            # STANDARD CASE
            # e.g.  local:      ./to/something      [/tmp/to/something]
            #       remote:     something
            # -----------------------------
            # SPECIAL CASE  .
            # e.g.  local:      .                   [/tmp]
            #                   (with content f1, f2)
            #       remote:     tmp/f1, tmp/f2
            # -----------------------------
            # SPECIAL CASE [./././]*
            # e.g.  local:      ./to/adir/*         [/tmp/to/adir]
            #                   (with content f1, f2)
            #       remote:     f1, f2
            # TODO * not supported for now

            fpath = p.resolve()
            rpath = Path(fpath.name)

            log.d(f"p(f) = {p}")

            log.d(f"rpath(f) = {rpath}")

            sendfile = (fpath, rpath)
            log.i(f"Adding sendfile {sendfile}")
            sendfiles.appendleft(sendfile)

        def send_file(local_path: Path, remote_path: Path):
            nonlocal overwrite_policy
            nonlocal tot_bytes
            nonlocal n_files
            nonlocal errors
            nonlocal preview_total_size

            progressor = None

            # Create the file info for the local file, but set the
            # remote path as name
            finfo = create_file_info(local_path, name=str(remote_path))

            if not finfo:
                return

            log.i(f"send_file finfo: {j(finfo)}")
            fsize = finfo.get("size")
            ftype = finfo.get("ftype")

            if ftype == FTYPE_FILE:
                # Case: FILE => try to open the file and then transfer

                # Before invoke next(), try to open the file for real.
                # At least we are able to detect any error (e.g. perm denied)
                # before say the server that the transfer is began
                log.d("Trying to open file before initializing transfer")

                try:
                    local_fd = local_path.open("rb")
                    log.d(f"Opened: {local_path}")
                except FileNotFoundError:
                    errors.append(create_error_of_response(ClientErrors.NOT_EXISTS,
                                                             q(next_file_local)))
                    return
                except PermissionError:
                    errors.append(create_error_of_response(ClientErrors.PERMISSION_DENIED,
                                                             q(next_file_local)))
                    return
                except OSError as oserr:
                    errors.append(create_error_of_response(ClientErrors.ERR_2,
                                                           os_error_str(oserr),
                                                            q(next_file_local)))
                    return
                except Exception as exc:
                    errors.append(create_error_of_response(ClientErrors.ERR_2,
                                                           exc,
                                                           q(next_file_local)))
                    return

            log.d("doing a put_next")

            put_next_resp = conn.call({
                RequestsParams.PUT_NEXT_FILE: finfo,
                RequestsParams.PUT_NEXT_OVERWRITE: overwrite_policy
            })

            if is_error_response(put_next_resp):
                log.w("Received error response for next()")
                errors += put_next_resp.get("errors")
                # All the errors will be reported at the end
                return

            if not is_data_response(put_next_resp, ResponsesParams.PUT_NEXT_STATUS):
                raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

            status = put_next_resp.get("data").get(ResponsesParams.PUT_NEXT_STATUS)
            already_exists = put_next_resp.get("data").get(ResponsesParams.PUT_NEXT_ALREADY_EXISTS)

            # Case: DIR => no transfer
            if ftype == FTYPE_DIR:
                log.d("Sent a DIR, nothing else to do")
                if preview and not already_exists:
                    if str(remote_path) != ".": # dirty fix, I won't want to see . in the preview
                        print(green(f"+ [{size_str_justify(0)}] {remote_path}"))
                return

            # Case: FILE

            # Possible responses:
            # "accepted" => add the file to the transfer socket
            # "refused"  => do not add the file to the transfer socket
            # "ask_overwrite" => ask to the user and tell it to the esd
            #                    we got this response only if the overwrite
            #                    policy told to the server is PROMPT

            # First of all handle the ask_overwrite, and contact the esd
            # again for tell the response
            if status == ResponsesParams.PUT_NEXT_STATUS_UNCERTAIN:
                if not already_exists:
                    log.w("WTF the remote is uncertain about, if the file does not exists?")

                # Ask the user what to do

                remote_finfo = put_next_resp.get("data").get(ResponsesParams.PUT_NEXT_FILE_INFO)

                timer.stop() # Don't take the user time into account
                current_overwrite_decision, overwrite_policy = self._ask_overwrite(
                    local_info=finfo,
                    remote_info=remote_finfo,
                    current_policy=overwrite_policy
                )
                timer.start()

                if current_overwrite_decision == OverwritePolicy.NO:
                    log.i(f"Skipping {remote_path}")
                    return

                # If overwrite policy is NEWER or YES we have to tell it
                # to the server so that it will take the right action
                put_next_resp = conn.call({
                    RequestsParams.PUT_NEXT_FILE: finfo,
                    RequestsParams.PUT_NEXT_OVERWRITE: current_overwrite_decision
                })

                if is_success_response(put_next_resp):
                    log.d("Transfer can actually begin")
                elif is_error_response(put_next_resp):
                    log.w("Transfer cannot be initialized due to remote error")
                    errors += put_next_resp.get("errors")
                    # All the errors will be reported at the end
                    return
                else:
                    raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

            # The current put_next_resp is either the original one
            # or the one got after the ask_overwrite response we sent
            # to the server.
            # By the way, it should not contain an ask_overwrite
            # since we specified a policy among YES/NEWER

            resp_data = ensure_data_response(put_next_resp, ResponsesParams.PUT_NEXT_STATUS)
            status = resp_data.get(ResponsesParams.PUT_NEXT_STATUS)

            if status == ResponsesParams.PUT_NEXT_STATUS_REFUSED:
                log.i(f"Skipping {remote_path}")
                return

            if status != ResponsesParams.PUT_NEXT_STATUS_ACCEPTED:
                raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

            # File has been accepted by the remote, we can begin the transfer

            if preview:
                # Just a preview, nothing to transfer
                print(green(f"+ [{size_str_justify(fsize)}] {remote_path}"))
                preview_total_size += fsize
                return

            if not quiet:
                progressor = FileProgressor(
                    fsize,
                    description="PUT " + str(remote_path),
                    color_progress=PROGRESS_COLOR,
                    color_success=SUCCESS_COLOR,
                    color_error=ERROR_COLOR
                )

            # File is already opened
            source = local_fd

            if use_mmap:
                try:
                    # try to mmap the file to memory
                    source = mmap.mmap(local_fd.fileno(), 0,
                                       prot=mmap.PROT_READ)
                except Exception as ex:
                    log.w(f"mmap failed, will read directly from file for reason: {ex}")

            cur_pos = 0
            crc = 0

            while cur_pos < fsize:
                readlen = min(fsize - cur_pos, chunk_size)

                chunk = source.read(readlen)
                chunk_len = len(chunk)

                log.h(f"Read chunk of {chunk_len}B")

                # CRC check update
                if do_check:
                    crc = zlib.crc32(chunk, crc)

                if not chunk:
                    log.i(f"Finished {local_path}")
                    break

                transfer_socket.send(chunk)

                cur_pos += chunk_len
                tot_bytes += chunk_len
                if not quiet:
                    progressor.update(cur_pos)

            log.i(f"DONE {local_path}")
            log.d(f"- crc = {crc}")

            if do_check:
                transfer_socket.send(itob(crc, 4))

            local_fd.close()
            if source != local_fd:
                source.close() # mmap

            n_files += 1
            if not quiet:
                progressor.success()


        while sendfiles:
            log.i("Putting another file info")
            next_file = sendfiles.pop()

            # Check what is this
            # 1. Non existing: skip
            # 2. Hidden: skip if is_hidden = True
            # 2. A file: send it directly (parent dirs won't be replicated)
            # 3. A dir: send it recursively
            next_file_local, next_file_remote = next_file

            if no_hidden and is_hidden(next_file_local):
                log.d(f"Not sending {next_file_local} since no_hidden is True")
            elif next_file_local.is_file():
                # Send it directly
                log.d("-> is a FILE")
                send_file(next_file_local, next_file_remote)
            elif next_file_local.is_dir():
                # Send it recursively

                log.d("-> is a DIR")

                try:
                    dir_files: List[Path] = sorted(list(next_file_local.iterdir()), reverse=False)
                except FileNotFoundError:
                    errors.append(create_error_of_response(ClientErrors.NOT_EXISTS,
                                                             q(next_file_local)))
                    continue
                except PermissionError:
                    errors.append(create_error_of_response(ClientErrors.PERMISSION_DENIED,
                                                             q(next_file_local)))
                    continue
                except OSError as oserr:
                    errors.append(create_error_of_response(ClientErrors.ERR_2,
                                                           os_error_str(oserr),
                                                            q(next_file_local)))
                    continue
                except Exception as exc:
                    errors.append(create_error_of_response(ClientErrors.ERR_2,
                                                           exc,
                                                           q(next_file_local)))
                    continue


                # Directory found

                if sync:
                    log.d("Sending the directory finfo as first since sync is True")
                    send_file(next_file_local, next_file_remote)

                if dir_files:
                    # standard case
                    log.i("Found a filled directory: adding all inner files to remaining_files")
                    for file_in_dir in dir_files:
                        sendfile = (file_in_dir, next_file_remote / file_in_dir.name)
                        log.i(f"Adding sendfile {sendfile}")
                        sendfiles.appendleft(sendfile)
                elif not sync: # if sync is True the finfo is already sent
                    log.i("Found an empty directory")
                    log.d("Pushing an info for the empty directory")
                    send_file(next_file_local, next_file_remote)
            else:
                log.w(f"Failed to send '{next_file_local}': unknown file type, doing nothing")

        log.i("Sending DONE")

        put_done_resp = conn.call({})
        ensure_success_response(put_done_resp)

        # Wait for completion
        outcome_resp = conn.read_json()
        outcome_resp_data = ensure_data_response(outcome_resp, ResponsesParams.PUT_OUTCOME)

        timer.stop()
        elapsed_s = timer.elapsed_s()

        # transfer_socket.close()

        # Take outcome and (eventually) errors out of the resp
        outcome = outcome_resp_data.get("outcome")
        outcome_errors = outcome_resp_data.get("errors")


        if outcome_errors:
            log.w("Response has errors")
            errors += outcome_errors

        log.i(f"PUT outcome: {outcome}")

        if preview:
            if sync:
                sync_oks = outcome_resp_data.get("sync_oks")
                for sync_ok in sync_oks:
                    print(red(f"- {sync_ok}"))
            print(f"Upload size: {size_str(preview_total_size)}")
            return # Nothing else to do

        if n_files > 0:
            print("")
        print(f"PUT outcome:  {outcome_str(outcome)}")
        print("-----------------------")
        print(f"Files:        {n_files} ({size_str(tot_bytes)})")
        print(f"Time:         {duration_str_human(round(elapsed_s))}")
        print(f"Avg. speed:   {speed_str(tot_bytes / elapsed_s)}")

        # Any error? (e.g. permission denied)
        if errors:
            print("-----------------------")
            print(f"PUT Errors:   {len(errors)}")
            for idx, err in enumerate(errors):
                    err_str = formatted_error_from_error_of_response(err)
                    print(f"{idx + 1}. {err_str}")

        # SYNC stats
        if sync:
            outcome_sync_rm_oks = outcome_resp_data.get("sync_oks")
            outcome_sync_rm_errors = outcome_resp_data.get("sync_errors")

            print("=======================")
            print(f"SYNC removed: {len(outcome_sync_rm_oks)}")
            for idx, removed in enumerate(outcome_sync_rm_oks):
                print(f"{idx + 1}. {removed}")

            if outcome_sync_rm_errors:
                print("-----------------------")
                print(f"SYNC errors:  {len(outcome_sync_rm_errors)}")
                for idx, err in enumerate(outcome_sync_rm_errors):
                    print(f"{idx + 1}. {err}")

    def _mvcp(self,
              args: Args,
              primitive: Callable[[Path, Path], bool],
              primitive_name: str = "mv/cp",
              error_callback: Callable[[Exception, Path, Path], None] = None):


        # mv <src>... <dest>
        #
        # A1  At least two parameters
        # A2  If a <src> doesn't exist => IGNORES it
        #
        # 2 args:
        # B1  If <dest> exists
        #     B1.1    If type of <dest> is DIR => put <src> into <dest> anyway
        #
        #     B1.2    If type of <dest> is FILE
        #         B1.2.1  If type of <src> is DIR => ERROR
        #         B1.2.2  If type of <src> is FILE => OVERWRITE
        # B2  If <dest> doesn't exist => preserve type of <src>
        #
        # 3 args:
        # C1  if <dest> exists => must be a dir
        # C2  If <dest> doesn't exist => ERROR


        mvcp_args = []
        for f in args.get_positionals():
            mvcp_args += self._local_paths(f)

        if not mvcp_args or len(mvcp_args) < 2:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        dest = mvcp_args.pop() # dest is always the last one
        sources = mvcp_args    # we can treat mvcp_args as sources since dest is popped

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not dest.is_dir():
                log.e("'%s' must be an existing directory", dest)
                raise CommandExecutionError(errno_str(ErrorsStrings.NOT_A_DIRECTORY, q(dest)))

        # Every other constraint is well handled by shutil.move() or shutil.copytree()

        for src in sources:
            log.i(">> %s '%s' '%s'", primitive_name.upper(), src, dest)

            try:
                primitive(src, dest)
            except Exception as ex:
                if error_callback:
                    error_callback(ex, src, dest)
                else:
                    raise ex


    def _rmvcp(self,
               args: Args,
               api: Callable[[List[str], str], Response],
               api_name: str = "RMV/RCP"):
        paths = []
        for p in args.get_positionals():
            paths += self._remote_paths(p)

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        dest = paths.pop()

        if not dest or not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> %s %s -> %s", api_name, str(paths), dest)

        resp = api(paths, dest)
        ensure_success_response(resp)

    @classmethod
    def _rm(cls, path: Path) -> Optional[str]:

        log.i("RM '%s'", path)

        error = None

        def handle_rm_error(exc: Exception, p: Path):
            nonlocal error

            if isinstance(exc, PermissionError):
                error = errno_str(ClientErrors.RM_PERMISSION_DENIED,
                                        q(p))
            elif isinstance(exc, FileNotFoundError):
                error = errno_str(ClientErrors.RM_NOT_EXISTS,
                                        q(p))
            elif isinstance(exc, OSError):
                error = errno_str(ClientErrors.RM_OTHER_ERROR,
                                        os_error_str(exc),
                                        q(p))
            else:
                error = errno_str(ClientErrors.RM_OTHER_ERROR,
                                        exc,
                                        q(p))

        rm(path, error_callback=handle_rm_error)

        return error

    @classmethod
    def _xstat(cls,
             args: Args,
             data_provider: Callable[..., Optional[List[FileInfo]]]):

        paths = args.get_positionals()

        stat_result = data_provider(paths)

        if stat_result is None:
            raise CommandExecutionError()

        print_files_info_list(
            stat_result,
            show_file_type=True,
            show_hidden=True,
            show_size=True,
            show_perm=True,
            show_owner=True,
            compact=False,
            file_info_renderer=file_info_pretty_sstr
        )

    @classmethod
    def _xls(cls,
             args: Args,
             data_provider: Callable[..., Optional[List[FileInfo]]],
             data_provider_name: str = "LS"):

        # Do not wrap here in a Path here, since the provider could be remote
        path = args.get_positional()
        reverse = Ls.REVERSE in args
        show_hidden = Ls.SHOW_ALL in args

        # Sorting
        sort_by = ["name"]

        if Ls.SORT_BY_SIZE in args:
            sort_by.append("size")
        if Ls.GROUP in args:
            sort_by.append("ftype")

        fetch_details = Ls.SHOW_SIZE in args or Ls.SHOW_DETAILS in args or \
                        "size" in sort_by or "ftype" in sort_by

        log.i(">> %s %s (sort by %s%s)",
              data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")

        ls_result = data_provider(path,
                                  sort_by=sort_by, reverse=reverse,
                                  hidden=show_hidden, details=fetch_details)

        if ls_result is None:
            raise CommandExecutionError()

        print_files_info_list(
            ls_result,
            show_file_type=Ls.SHOW_DETAILS in args,
            show_hidden=show_hidden,
            show_size=Ls.SHOW_SIZE in args or Ls.SHOW_DETAILS in args,
            show_perm=Ls.SHOW_DETAILS in args,
            show_owner=Ls.SHOW_DETAILS in args,
            compact=Ls.SHOW_DETAILS not in args
        )

    @classmethod
    def _xtree(cls,
               args: Args,
               data_provider: Callable[..., Optional[FileInfoTreeNode]],
               data_provider_name: str = "TREE"):

        path = args.get_positional()
        reverse = Tree.REVERSE in args
        show_hidden = Tree.SHOW_ALL in args
        max_depth = args.get_option_param(Tree.MAX_DEPTH, default=None)
        details = Tree.SHOW_SIZE in args or Tree.SHOW_DETAILS in args

        sort_by = ["name"]

        if Tree.SORT_BY_SIZE in args:
            sort_by.append("size")
        if Tree.GROUP in args:
            sort_by.append("ftype")

        log.i(">> %s %s (sort by %s%s)",
              data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")

        tree_result: FileInfoTreeNode = data_provider(
            path,
            sort_by=sort_by, reverse=reverse,
            hidden=show_hidden, max_depth=max_depth,
            details=details
        )

        if tree_result is None:
            raise CommandExecutionError()

        print_files_info_tree(tree_result,
                              max_depth=max_depth,
                              show_hidden=show_hidden,
                              show_size=details)


    def _xfind(self,
               args: Args,
               data_provider: Callable[..., Optional[List[FileInfo]]],
               data_provider_name: str = "FIND",
               findings_adder: Callable[[List[FileInfo]], str] = None):

        # Do not wrap here in a Path here, since the provider could be remote
        path = args.get_positional()
        name = args.get_option_param(Find.NAME)
        regex = args.get_option_param(Find.REGEX)
        insensitive = Find.CASE_INSENSITIVE in args
        ftype = args.get_option_param(Find.TYPE)
        details = Find.SHOW_DETAILS in args
        max_depth = args.get_option_param(Find.MAX_DEPTH)

        if ftype in ["f", FTYPE_FILE]:
            ftype = FTYPE_FILE
        elif ftype in ["d", FTYPE_DIR]:
            ftype = FTYPE_DIR

        log.i(">> %s %s",
              data_provider_name, path)

        find_result = data_provider(path,
                                    name=name, regex=regex,
                                    case_sensitive=not insensitive,
                                    ftype=ftype, details=details,
                                    max_depth=max_depth)

        if find_result is None:
            raise CommandExecutionError()

        finding_letter = None
        if findings_adder:
            log.d("Adding find result to findings")
            finding_letter = findings_adder(find_result)
            findings_justify = len(str(len(find_result)))

        def file_info_sstr_find(
                info: FileInfo,
                show_file_type: bool = False,
                show_size: bool = False,
                show_hidden: bool = False,
                show_perm: bool = False,
                show_owner: bool = False,
                owner_user_justify: int = 0,  # -l
                owner_group_justify: int = 0,  # -l
                index: int = None) -> Optional[StyledString]:

            finfo_str = file_info_inline_sstr(
                info,
                show_file_type=show_file_type,
                show_size=show_size,
                show_hidden=show_hidden,
                show_perm=show_perm,
                show_owner=show_owner,
                owner_user_justify=owner_user_justify,
                owner_group_justify=owner_group_justify
            )

            if finfo_str:
                if finding_letter:
                    prefix = ("$" + finding_letter + str(index + 1)).rjust(findings_justify + 2) + " "
                    finfo_str.string = prefix + finfo_str.string
                    finfo_str.styled_string = prefix + finfo_str.styled_string
                return finfo_str


        print_files_info_list(
            find_result,
            show_hidden=True,
            compact=False,
            show_perm=details,
            show_owner=details,
            show_file_type=details,
            show_size=details,
            file_info_renderer=file_info_sstr_find
        )

    def _add_local_findings(self, find_result: List[FileInfo]) -> Optional[str]:
        curpwd = Path.cwd()

        letter = self._local_finding_letter

        log.i("Adding %d local findings from pwd = %s (letter %s)",
              len(find_result), str(curpwd), letter)

        self._local_findings[letter] = Findings(curpwd, find_result)
        self._local_finding_letter = chrnext(letter, start="a", end="z")

        return letter


    def _add_remote_findings(self, find_result: List[FileInfo]) -> Optional[str]:
        if not self.is_connected_to_sharing():
            log.w("Can't add remote findings, not connected to a sharing")
            return None

        letter = self._remote_finding_letter

        currpwd = self.connection.current_rcwd()
        log.i("Adding %d remote findings from rcwd = %s (letter %s)",
              len(find_result), currpwd, letter)

        self._remote_findings[letter] = Findings(currpwd, find_result)
        self._remote_finding_letter = chrnext(letter, start="A", end="Z")

        return letter

    def _clear_remote_findings(self):
        log.d("Clearing remote findings")
        self._remote_findings.clear()
        self._remote_finding_letter = "A"

    def _local_path(self, path_or_finding_pattern: str, default: str = "") \
            -> Path:
        return self.__local_paths(path_or_finding_pattern, default)[0]

    def _local_paths(self, path_or_finding_pattern: str, default: str = "") \
            -> List[Path]:
        return self.__local_paths(path_or_finding_pattern, default)

    def __local_paths(self, path_or_finding_pattern: str, default: str = "") \
            -> List[Path]:
        log.i(f"Computing local path of '{path_or_finding_pattern}'")

        return self.__paths(
            path_or_finding_pattern,
            findings_provider=self.get_local_findings,
            path_builder=lambda path, finfo: path / finfo.get("name"),
            path_filter=lambda p: LocalPath(p, default)
        )


    def _remote_path(self, path_or_finding_pattern: str) \
            -> str:
        return self.__remote_paths(path_or_finding_pattern)[0]

    def _remote_paths(self, path_or_finding_pattern: str) \
            -> List[str]:
        return self.__remote_paths(path_or_finding_pattern)

    def __remote_paths(self, path_or_finding_pattern: str) \
            -> List[str]:
        log.i(f"Computing remote path of '{path_or_finding_pattern}'")

        return self.__paths(
            path_or_finding_pattern,
            findings_provider=self.get_remote_findings,
            path_builder=lambda path, finfo: os.path.join(path, finfo.get("name")),
        )

    def __paths(self,
                path_or_finding_pattern: str,
                findings_provider: Callable[[str], Findings],
                path_builder: Callable[[Union[Path, str], FileInfo], Union[Path, str]],
                path_filter: Callable[[Union[Path, str]], Union[Path, str]] = lambda p: p) \
            -> List[Union[Path, str]]:
        # TODO if the filename has the form of the finding we can't treat it...
        #  found a way such as escape $ or use double $$

        if not path_or_finding_pattern:
            return [path_filter(path_or_finding_pattern)]

        paths = []

        findings = findings_provider(path_or_finding_pattern)
        if findings:
            for info in findings.infos:
                paths.append(path_filter(path_builder(findings.path, info)))
        else:
            # Not a finding, just a regular path
            paths.append(path_filter(path_or_finding_pattern))

        return paths

    def get_local_findings(self, pattern: str) -> Optional[Findings]:
        return self._get_findings(self._local_findings, pattern)

    def get_remote_findings(self, pattern: str) -> Optional[Findings]:
        return self._get_findings(self._remote_findings, pattern)

    @classmethod
    def _get_findings(cls, findings_dict: Dict[str, Findings], pattern: str) -> Optional[Findings]:
        log.d("Looking for findings in pattern '%s'", pattern)

        match = re.fullmatch(Client.FINDINGS_RE, pattern)
        if match:
            letter, idx_start, idx_end = match.groups()
            if not idx_end:
                idx_end = idx_start

            idx_start = int(idx_start) - 1
            idx_end = int(idx_end) - 1

            # The path contains a valid finding pattern
            log.d("Found finding match in path (letter=%s | idx_start=%d | idx_end=%d)",
                  letter, idx_start + 1, idx_end + 1)

            # Check whether we actually have the finding
            findings_of_letter: List[FileInfo]
            searchpath: Union[str, Path]

            findings_for_letter = findings_dict.get(letter)
            if findings_for_letter and findings_for_letter.infos:
                log.d("Findings for letter %s found - search path was '%s'",
                      letter, findings_for_letter.path)

                i = idx_start

                findings_path = findings_for_letter.path
                findings_infos = []

                while i <= idx_end and i < len(findings_for_letter.infos):
                    log.d("Finding for '%s' found: '%s'", match.group(),
                          findings_for_letter.infos[i])
                    findings_infos.append(findings_for_letter.infos[i])
                    i += 1

                return Findings(findings_path, findings_infos)

            log.w("Findings not found: '%s'", match.group())

        return None

    def _get_current_sharing_connection_or_create_from_sharing_location_args(
            self, args: Args, sharing_ftype: FileType) -> Connection:
        """
        Returns the current sharing, server connection if already established.
        Otherwise tries to create a new one considering the first arg of 'args'
        as a sharing location (popping the arg).
        """

        if self.is_connected_to_server() and self.is_connected_to_sharing():
            log.i("Providing already established sharing connection")
            return self.connection

        # Create temporary connection
        log.i("No established sharing connection; creating a new one")

        pargs = args.get_positionals()

        if not pargs:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        sharing_location = SharingLocation.parse(pargs.pop(0))
        return self._create_sharing_connection_from_sharing_location(
            sharing_location=sharing_location, sharing_ftype=sharing_ftype
        )


    def _get_current_server_connection_or_create_from_server_location_args(
            self, args: Args, connect: bool) -> Connection:
        """
        Returns the current server connection if already established.
        Otherwise tries to create a new one considering the first arg of 'args'
        as a server location (popping the arg).
        """

        if self.is_connected_to_server():
            log.i("Providing already established server connection")
            return self.connection

        # Create temporary connection
        log.i("No established server connection; creating a new one")

        pargs = args.get_positionals()

        if not pargs:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        server_location = ServerLocation.parse(pargs.pop(0))
        return self._create_server_connection_from_server_location(
            server_location, connect=connect)


    def _create_sharing_connection_from_sharing_location(
            self,
            sharing_location: SharingLocation,
            sharing_ftype: FileType = None) -> Optional[Connection]:
        """
        Creates a new SharingConnection (and thus a ServerConnection)
        for the given sharing location.
        """

        conn = self._create_server_connection(
            connect=True,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=sharing_ftype,
        )

        if not conn or not conn.is_connected_to_server():
            raise CommandExecutionError(ClientErrors.SERVER_NOT_FOUND)

        self._create_sharing_connection_from_server_connection(
            connection=conn,
            sharing_location=sharing_location,
        )

        if not conn.is_connected_to_sharing():
            raise CommandExecutionError(ClientErrors.SHARING_NOT_FOUND)

        return conn


    def _create_server_connection_from_server_location(
            self, server_location: ServerLocation, connect: bool) -> Connection:
        """
        Creates a new ServerConnection for the given server location.
        """
        return self._create_server_connection(
            connect=connect,
            server_name=server_location.name,
            server_ip=server_location.ip,
            server_port=server_location.port
        )


    def _create_server_connection(
            self, connect: bool,
            server_name: str = None, server_ip: str = None, server_port: int = None,
            sharing_name: str = None, sharing_ftype: FileType = None) -> Connection:
        """
        Real method that creates a server connection based on the params.
        The connection is created as smartly as possible.
        In particular:
        1.  If both IP and PORT are specified, the connection is tried to be
            established (just) directly
        2.  If only IP is specified, the connection is tried to be established
            directly but a scan is performed for it fails (maybe it is on non default port?)
        3.  If IP is not specified, a scan is involved and the server is filtered
            based on the given filter (server name, sharing name, sharing ftype)

        For 1. and 2. the connection is attempted to be established with and
        without SSL since we can't know whether the server use it or not
        without perform a preliminary scan.

        The server connection is then authenticated if 'connect' is True,
        otherwise an unconnected connection is returned (e.g. for unauthenticated
        method such as ping, list, ...)
        """

        # server_port = server_port or DEFAULT_SERVER_PORT

        just_directly = False
        server_conn = None
        real_server_info = None

        if server_ip:
            server_ssl = False
            # TODO test direct connection
            if server_port:
                log.d("Server IP and PORT are specified: trying to connect directly")
                just_directly = True # Everything specified => won't perform a scan
                attempt_port = server_port
                # auto_server_info["port"] = server_port
            else:
                log.d("Server IP is specified: trying to connect directly to the default port")
                attempt_port = DEFAULT_SERVER_PORT
                # auto_server_info["port"] = DEFAULT_SERVER_PORT

            while True: # actually two attempts are done: with/without SSL


                try:
                    # Create a connection
                    server_conn = ConnectionMinimal(
                        server_ip=server_ip,
                        server_port=attempt_port,
                        server_ssl=server_ssl
                    )

                    # Check if it is up
                    # (e.g. if the port was not specified in case 2. maybe the user
                    # want to perform a scan instead of connect to the default port,
                    # by checking if the connection is up we are able to figure out that)

                    resp = server_conn.info()
                    ensure_data_response(resp)

                    real_server_info = resp.get("data")
                    log.d("Connection established is UP, retrieved server info\n%s",
                          j(real_server_info))

                    # Fill the uncomplete server info with the IP/port we used to connect
                    break
                except:
                    log.w("Connection cannot be established directly %s SSL",
                          "with" if server_ssl else "without")
                    if server_conn:
                        # Invalidate connection
                        server_conn.destroy_connection()
                    server_conn = None

                if not server_ssl:
                    log.d("Trying again enabling SSL before giving up")
                    server_ssl = True
                else:
                    log.e("Connection can't be directly established neither with nor without SSL")
                    break

            # Check whether the connection has been established

            if real_server_info: # connection established directly
                log.d("Connection has been established directly without perform a DISCOVER")
                # Wraps the already established server conn in a ServerConnection
                # associated with the right server info


                if self._server_info_satisfy_constraints(
                        # DO not check server identity: this is needed for allow servers
                        # behind NAT to be reached without know the real internal IP/port
                        real_server_info,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND directly")
                    server_conn = Connection(
                        server_ip=server_ip,
                        server_port=attempt_port,
                        server_info=real_server_info,
                        socket=server_conn._stream._socket
                    )
            elif server_conn:
                # Invalidate connection
                server_conn.destroy_connection()
                server_conn = None

        # Eventually performs the scan
        if not server_conn:
            if just_directly:
                log.d("Connection not established directly and DISCOVER won't be "
                      "performed since IP and PORT has been specified both")
            else:
                log.d("Will perform a DISCOVER for establish server connection")
                real_server_info = self._discover_server(
                    server_name=server_name, server_ip=server_ip, server_port=server_port,
                    sharing_name=sharing_name, sharing_ftype=sharing_ftype
                )

                if self._server_info_satisfy_constraints_full(
                        real_server_info,
                        server_name=server_name, server_ip=server_ip, server_port=server_port,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND w/ discover")
                    # IP and port can be provided from real_server_info
                    # since came from the discover and thus are real
                    try:
                        server_conn = Connection(
                            server_ip=real_server_info.get("ip"),
                            server_port=real_server_info.get("port"),
                            server_info=real_server_info
                        )
                    except:
                        log.w("Connection establishment failed even if found with DISCOVER")

        if not server_conn:
            log.e("Connection can't be established")
            raise CommandExecutionError(ErrorsStrings.CONNECTION_CANT_BE_ESTABLISHED)

        # We have a valid TCP connection with the server
        log.i("Connection established with %s:%d",
              server_conn.server_ip(),
              server_conn.server_port())

        # Version check
        if APP_VERSION != server_conn.server_info.get("version"):
            log.w("Server version (%s) doesn't match client one (%s): bad things might happen",
                  server_conn.server_info.get("version"), APP_VERSION)

        # We have a valid TCP connection with the server
        # log.d("-> same as %s:%d",
        #       server_conn.server_info.get("ip"),
        #       server_conn.server_info.get("port"))


        # Check whether we have to do connect()
        # (It might be unnecessary for public server api such as ping, info, list, ...)
        if not connect:
            return server_conn

        log.d("Will perform authentication (if required by the esd)")
        passwd = None

        # Ask the password if the sharing is protected by auth
        if real_server_info.get("auth"):
            log.i("Server '%s' is protected by password", real_server_info.get("name"))
            passwd = getpass()
        else:
            log.i("Server '%s' is not protected", real_server_info.get("name"))

        # Performs connect() (and authentication)
        resp = server_conn.connect(passwd)
        ensure_success_response(resp)

        return server_conn


    def _discover_server(
            self,
            server_name: str = None, server_ip: str = None,
            server_port: int = None, sharing_name: str = None,
            sharing_ftype: FileType = None) -> Optional[ServerInfoFull]:
        """
        Performs a discover looking for a server that satisfy the given filters.
        """

        server_info: Optional[ServerInfoFull] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfoFull) -> bool:
            nonlocal server_info

            log.d("Handling DISCOVER response from %s\n%s", str(client_endpoint), str(a_server_info))

            if self._server_info_satisfy_constraints_full(
                a_server_info,
                server_ip=server_ip,
                server_port=server_port,
                server_name=server_name,
                sharing_name=sharing_name,
                sharing_ftype=sharing_ftype
            ):
                server_info = a_server_info
                return False    # Stop DISCOVER

            return True         # Continue DISCOVER

        self._discover(
            discover_addr=server_ip or ADDR_BROADCAST,
            response_handler=response_handler,
            progress=True,
            success_if_ends=False
        )

        return server_info


    def _connect(self, server_location: ServerLocation):
        if type(server_location) != ServerLocation:
            raise TypeError(f"expected ServerLocation, found {type(server_location)}")

        # Just in case check whether we already connected to the right one
        if self.is_connected_to_server():
            if self._server_info_satisfy_server_location(
                    self.connection.server_info,
                    server_location):
                log.w("Current connection already satisfy server location constraints")
                return

        # Actually create the connection
        newconn = self._create_server_connection_from_server_location(
            server_location,
            connect=True
        )

        if not newconn or not newconn.is_connected_to_server():
            raise CommandExecutionError(ClientErrors.SERVER_NOT_FOUND)

        log.i("Server connection established")

        if self.is_connected_to_server():
            log.i("Disconnecting current server connection before set the new one")
            # self.server_connection.destroy_connection()
            # self.server_connection.disconnect()
            self.destroy_connection()

        self.connection = newconn


    def _open(self, sharing_location: SharingLocation):
        new_conn: Optional[Connection] = None

        if type(sharing_location) != SharingLocation:
            raise TypeError(f"expected SharingLocation, found {type(sharing_location)}")

        # Check whether we are connected to a server which owns the
        # sharing we are looking for, otherwise performs a scan
        if self.is_connected_to_server():
            # Check whether the sharing is actually among the sharings of
            # this server
            if self._server_info_satisfy_sharing_location(
                    self.connection.server_info,
                    sharing_location
            ):
                # The sharing is among the sharings of this connection
                log.d("The sharing we are looking for is among the sharings"
                      " of the already established server connection")

                new_conn = self.connection

                # Check whether we are already connected to it, just in case
                if self.is_connected_to_sharing() and \
                        self.connection.current_sharing_name() == sharing_location.name:
                    log.w("Current sharing connection already satisfy the sharing constraints")

                    # Connection might be down, at least try to ping the remote
                    ping_resp = None

                    try:
                        ping_resp = self.connection.ping()
                    except:
                        # Will handle an invalid response here below
                        pass

                    if is_data_response(ping_resp) and ping_resp.get("data") == "pong":
                        log.d("Received valid response from the server we are already connected to - OK")
                        return  # nothing more to do
                    else:
                        log.e("Current connection is broken; destroying it")
                        self.destroy_connection()
                else:
                    # Do an open() with this server connection
                    # (the sharing should be within its sharings since we checked
                    # it with server_info_satisfy_sharing_location)
                    self._create_sharing_connection_from_server_connection(
                        self.connection,
                        sharing_location=sharing_location
                    )

        # Have we found the sharing yet or do we have to perform a scan?
        if not new_conn or not new_conn.is_connected_to_sharing():
            # Performs a scan
            new_conn = self._create_sharing_connection_from_sharing_location(
                sharing_location
            )

        if not new_conn or not new_conn.is_connected_to_sharing():
            log.e("Server or sharing connection establishment failed")
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Close current stuff (if the new connections are actually new and different)

        log.i("Closing current server connection before set the new one")
        if new_conn != self.connection:
            self.destroy_connection()

        # Just mark that the server connection has been created due open()
        # so that for symmetry close() will do disconnect() too
        if new_conn != self.connection:
            setattr(new_conn, "created_with_open", True)

        log.i("Server and sharing connection established")
        self.connection = new_conn

    @classmethod
    def _create_sharing_connection_from_server_connection(
            cls, connection: Connection, sharing_location: SharingLocation):
        """
        Given an already valid server connection, tries to establish a sharing
        connection to the sharing with the given name (=> does open())
        """

        if not connection or not connection.is_connected_to_server():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Create the sharing connection: open()

        open_resp = connection.open(sharing_location.name)
        ensure_success_response(open_resp)

        # Eventually rcd into the path specified
        # (the part after the last / of the sharing location)
        if sharing_location.path:
            log.d("Sharing location contains a path, rcd-ing into it")
            resp = connection.rcd(sharing_location.path)

            ensure_data_response(resp)
            log.d("Current rcwd: %s", connection.current_rcwd())

    @classmethod
    def _server_info_satisfy_server_location(cls,
                                             server_info: ServerInfo, server_location: ServerLocation):
        """ Whether 'server_info' satisfy 'server_location' """
        return cls._server_info_satisfy_constraints(
                server_info,
                server_name=server_location.name)

    @classmethod
    def _server_info_satisfy_sharing_location(cls,
                                              server_info: ServerInfo, sharing_location: SharingLocation):
        """ Whether 'server_info' satisfy 'sharing_location' """

        return cls._server_info_satisfy_constraints(
                server_info,
                server_name=sharing_location.server_name,
                sharing_name=sharing_location.name,
                sharing_ftype=FTYPE_DIR)

    @classmethod
    def _server_info_satisfy_constraints(cls,
                                         server_info: ServerInfo,
                                         server_name: str = None,
                                         sharing_name: str = None,
                                         sharing_ftype: FileType = None) -> bool:
        """ Whether 'server_info' satisfy the given filters """

        # Make a shallow copy
        server_info_full: ServerInfoFull = cast(ServerInfoFull, {**server_info})
        server_info_full["ip"] = None
        server_info_full["port"] = None

        return cls._server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_name,
            sharing_name=sharing_name,
            sharing_ftype=sharing_ftype)

    @classmethod
    def _server_info_satisfy_server_location_full(cls,
                                                  server_info_full: ServerInfoFull, server_location: ServerLocation):
        """ Whether 'server_info_full' satisfy the given 'server_location' """

        return cls._server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_location.name,
            server_ip=server_location.ip,
            server_port=server_location.port)

    @classmethod
    def _server_info_satisfy_sharing_location_full(cls,
                                                   server_info_full: ServerInfoFull, sharing_location: SharingLocation):
        """ Whether 'server_info_full' satisfy the given 'sharing_location' """

        return cls._server_info_satisfy_constraints_full(
            server_info_full,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=FTYPE_DIR)

    @classmethod
    def _server_info_satisfy_constraints_full(cls,
                                              server_info: ServerInfoFull,
                                              server_name: str = None, server_ip: str = None, server_port: int = None,
                                              sharing_name: str = None, sharing_ftype: FileType = None) -> bool:
        """
        Actually check if the given 'server_info' satisfy the given filters.
        """


        log.d("constr server name: %s", server_name)
        log.d("constr server ip: %s", server_ip)
        log.d("constr server port: %s", str(server_port))
        log.d("constr sharing name: %s", sharing_name)
        log.d("constr sharing ftype: %s", sharing_ftype)

        if not server_info:
            return False

        # Server name
        if server_name and (server_name != server_info.get("name")):
            log.d("Server info does not match the server name filter '%s'",
                  server_name)
            return False

        # Server IP
        if server_ip and (server_ip != server_info.get("ip")):
            log.d("Server info does not match the server ip filter '%s'",
                  server_ip)
            return False

        # Server  port
        if server_port and (server_port != server_info.get("port")):
            log.d("Server info does not match the server port filter '%d'",
                  server_port)
            return False

        # Sharing filter
        if sharing_name:
            for a_sharing_info in server_info.get("sharings"):
                # Sharing name check
                if sharing_name != a_sharing_info.get("name"):
                    log.d("Ignoring sharing which does not match the sharing name filter '%s'",
                          sharing_name)
                    continue

                # Sharing ftype check
                if sharing_ftype and a_sharing_info.get("ftype") != sharing_ftype:
                    log.d("Ignoring sharing which does not match the ftype filter '%s'", sharing_ftype)
                    log.w("Found a sharing with the right name but wrong ftype, wrong command maybe?")
                    # Notify it outside, the user probably wants to know what's happening
                    print_errors("WARNING: " + ErrorsStrings.NOT_ALLOWED_FOR_F_SHARING)
                    continue

                # FOUND
                log.i("Server info satisfies constraints")
                break
            else:
                log.w("Server info constraints satisfied but the specified "
                      "sharing can't be found")
                return False # Not found

        return True

    _OVERWRITE_POLICY_MAP = { # current, default
        None: (OverwritePolicy.YES, None),
        "y": (OverwritePolicy.YES, None),
        "n": (OverwritePolicy.NO, None),
        "yy": (OverwritePolicy.YES, OverwritePolicy.YES),
        "nn": (OverwritePolicy.NO, OverwritePolicy.NO),
        "NN": (OverwritePolicy.NEWER, OverwritePolicy.NEWER),
        "SS": (OverwritePolicy.DIFF_SIZE, OverwritePolicy.DIFF_SIZE),
        "NNSS": (OverwritePolicy.NEWER_DIFF_SIZE, OverwritePolicy.NEWER_DIFF_SIZE),
    }

    @classmethod
    def _ask_overwrite(cls,
                       local_info: FileInfo, remote_info: FileInfo,
                       current_policy: str) -> Tuple[str, str]:  # cur_decision, new_default
        """
        If the 'current_policy' is PROMPT asks the user whether override
        a file with name 'fname'.
        Returns a tuple tha contains the instant decision and eventually
        the new default (which is the same as before the user didn't opt for
        set a default action)
        """

        log.d("ask_overwrite - default policy: %s", str(current_policy))
        # Ask whether overwrite just once or forever
        cur_decision = current_policy
        new_default = current_policy

        # Ask until we get a valid answer
        while cur_decision == OverwritePolicy.PROMPT:
            overwrite_answer = input(f"""\
File already exists, overwrite it?
------------ LOCAL ---------------
{file_info_pretty_str(local_info)}
------------ REMOTE --------------
{file_info_pretty_str(remote_info)}
----------------------------------
y     : yes (default)
n     : no
yy    : yes - to all
nn    : no - to all
NN    : only if newer - to all
SS    : only if size is different - to all
NNSS  : only if newer OR size is different - to all
: """
)
            if not overwrite_answer:
                overwrite_answer = None

            decision = cls._OVERWRITE_POLICY_MAP.get(overwrite_answer)

            if not decision:
                log.w("Invalid answer, asking again")
                continue

            cur_decision, new_default = decision[0], decision[1] or new_default

        return cur_decision, new_default

    @classmethod
    def _discover(
            cls,
            response_handler: Callable[[Endpoint, ServerInfoFull], bool],
            discover_addr: str = ADDR_BROADCAST,
            progress: bool = False,
            success_if_ends: bool = True):
        """
        Actually performs the discover.
        The method is overcomplex basically just for handle the progress bar
        of the scan in a consistent manner, but otherwise is just a call
        to Discoverer.discover().
        """

        discover_timeout = get_setting(Settings.DISCOVER_WAIT)

        discover_start_t = time.monotonic_ns()

        DISCOVER_RUNNING = 0
        DISCOVER_TIMEDOUT = 1   # Timedout (can be good (e.g. scan) or bad (e.g. open)
        DISCOVER_FOUND = 2      # Completed (e.g. found a sharing)
        DISCOVER_ABORTED = 3    # CTRL+C

        discover_state = DISCOVER_RUNNING

        pbar = None
        pbar_done_lock = None

        if progress:
            K = 200  # This can be anything actually, but don't set it too small
                     # or the accuracy might be no enough
            pbar = SimpleProgressor(
                K,
                color_progress=PROGRESS_COLOR,
                color_success=SUCCESS_COLOR,
                color_error=ERROR_COLOR,
                progress_bar_renderer=ProgressBarRendererFactory.ascii(
                    # mark="\u2014" if is_unicode_supported() else "-",
                    mark=".",
                    prefix="|",
                    postfix="|")
            )

            pbar_done_lock = threading.Lock()

        def stop_pbar(state: int):
            if not progress:
                # Progress bar not used at all
                return

            # Update the state, but only if it is still running
            # Otherwise consider the first state the good one
            nonlocal discover_state

            with pbar_done_lock:
                if discover_state == DISCOVER_RUNNING:
                    log.d("discover_state will be %d", state)

                    if state == DISCOVER_TIMEDOUT:
                        # DISCOVER_TIMEDOUT can either be good or bad
                        if success_if_ends:
                            log.d("DISCOVER_TIMEDOUT => success")
                            pbar.success()
                        else:
                            log.d("DISCOVER_TIMEDOUT => error")
                            pbar.error(completed=True)
                    elif state == DISCOVER_FOUND:
                        # DISCOVER_FOUND is always a success
                        # DELETE_EOL for overwrite the bar
                        print(ansi.RESET_LINE, end="", flush=True)
                    elif state == DISCOVER_ABORTED:

                        # DISCOVER_ABORTED is always an error
                        # try:
                        #     print(f"\n\nY={y}\n\nX={x}\n")
                        # except Exception as ex:
                        #     print(f"getyx failed {ex}")
                        #     pass
                        # print(ansi.UP_LINE + ansi.RESET_LINE, end="", flush=True)
                        pass
                        print(ansi.UP_LINE + ansi.RESET_LINE, end="", flush=True)
                        pbar.error() # don't set completed=True, since is aborted in the middle
                    else:
                        log.w("Unexpected new discover state: %d", discover_state)

                    # Set the new state
                    discover_state = state


        def discover_ui():
            # In the meanwhile, show a progress bar

            for i in range(K):
                if discover_state != DISCOVER_RUNNING:
                    break

                # Update the count
                pbar.update(i)

                # Sleep for approximately discover_timeout / K
                # but for a better accuracy we have to see actually how remaining
                # time of discover we have

                t = time.monotonic_ns()
                sleep_t = (discover_timeout - (t - discover_start_t) * 1e-9) / (K - i)
                if sleep_t > 0:
                    time.sleep(sleep_t)

                # time.sleep(discover_timeout / K)

            stop_pbar(DISCOVER_TIMEDOUT)


        discover_ui_thread = None

        if progress:
            # Show the progress
            discover_ui_thread = threading.Thread(target=discover_ui)
            discover_ui_thread.start()

        # -----

        original_sigint_handler = signal.getsignal(signal.SIGINT)

        def custom_sigint_handler(sig, frame):
            # Seems an overkill, but what this handler does is stop the
            # the bar now (a lock is needed since shared with the ui thread)
            # and raise a custom exception so that easyshare.shell won't
            # print an empty line
            nonlocal discover_state
            log.d("SIGINT while discovering")

            signal.signal(signal.SIGINT, original_sigint_handler)

            stop_pbar(DISCOVER_ABORTED)

            raise HandledKeyboardInterrupt()

        # Set the custom handler
        signal.signal(signal.SIGINT, custom_sigint_handler)

        def response_handler_fix_update_pbar_after_discover(endpoint, server_info) -> bool:
            # This wrapper is needed in order to print as soon as possible a new
            # line with the progress bar after a server is found; so that we can
            # user LINE_UP + CLEAR_LINE for delete the progress bar in stop_bar()
            # without clearing a valid last line of text of the discovered server
            ret = response_handler(endpoint, server_info)
            pbar.update(pbar.partial, force=True)
            return ret

        timedout = Discoverer(
            discover_addr=discover_addr,
            response_handler=response_handler_fix_update_pbar_after_discover
        ).discover()

        # Restore the original handler
        signal.signal(signal.SIGINT, original_sigint_handler)

        # ------

        stop_pbar(DISCOVER_TIMEDOUT if timedout else DISCOVER_FOUND)

        if discover_ui_thread:
            # Wait for the ui
            discover_ui_thread.join()