import fcntl
import os
import pty
import select
import signal
import socket
import sys
import threading
import time
import tty
import zlib
from getpass import getpass
from pathlib import Path
from pwd import struct_passwd
from typing import Optional, Callable, List, Dict, Union, Tuple, cast

from Pyro5.errors import PyroError

from easyshare.args import Args as Args, ArgsParseError, PosArgsSpec, \
    VarArgsSpec, ArgsSpec, StopParseArgsSpec
from easyshare.common import transfer_port, DEFAULT_SERVER_PORT, SUCCESS_COLOR, PROGRESS_COLOR, BEST_BUFFER_SIZE, \
    ERROR_COLOR
from easyshare.consts import ansi
from easyshare.consts.net import ADDR_BROADCAST
from easyshare.endpoint import Endpoint
from easyshare.es.common import ServerLocation, SharingLocation
from easyshare.es.connections.server import ServerConnection, ServerConnectionMinimal
from easyshare.es.connections.sharing import SharingConnection
from easyshare.es.discover import Discoverer
from easyshare.es.errors import ClientErrors, ErrorsStrings, errno_str, print_errors, outcome_str
from easyshare.es.ui import print_files_info_list, print_files_info_tree, \
    sharings_to_pretty_str, server_info_to_pretty_str, server_info_to_short_str
from easyshare.helps.commands import Commands, is_special_command, SPECIAL_COMMAND_MARK, Ls, Scan, Info, Tree, Put, Get, \
    ListSharings, Ping
from easyshare.logging import get_logger
from easyshare.protocol.responses import is_data_response, is_error_response, is_success_response, ResponseError, \
    create_error_of_response
from easyshare.protocol.services import Response, IPutService, IGetService, IRexecService, IRshellService
from easyshare.protocol.types import FileType, ServerInfoFull, FileInfoTreeNode, FileInfo, FTYPE_DIR, \
    OverwritePolicy, FTYPE_FILE, ServerInfo, create_file_info, PutNextResponse
from easyshare.sockets import SocketTcpOut
from easyshare.ssl import get_ssl_context
from easyshare.styling import red, bold
from easyshare.timer import Timer
from easyshare.utils.json import j
from easyshare.utils.measures import duration_str_human, speed_str, size_str
from easyshare.utils.os import ls, rm, tree, mv, cp, run_attached, get_passwd, is_unix, pty_attached, os_error_str
from easyshare.utils.path import LocalPath
from easyshare.utils.progress import ProgressBarRendererFactory
from easyshare.utils.progress.file import FileProgressor
from easyshare.utils.progress.simple import SimpleProgressor
from easyshare.utils.pyro import pyro_uri
from easyshare.utils.pyro.client import TracedPyroProxy
from easyshare.utils.str import q
from easyshare.utils.types import bytes_to_str, int_to_bytes, bytes_to_int

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
    if is_error_response(resp):
        raise CommandExecutionError(formatted_errors_from_error_response(resp))
    if not is_success_response(resp):
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)


def ensure_data_response(resp: Response, *data_fields):
    if is_error_response(resp):
        raise CommandExecutionError(formatted_errors_from_error_response(resp))
    if not is_data_response(resp):
        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
    for data_field in data_fields:
        if data_field not in resp.get("data"):
            raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)


def make_sharing_connection_api_wrapper(api, ftype: Optional[FileType]):
    def wrapper(client: 'Client', args: Args, _1: ServerConnection, _2: SharingConnection, **kwargs):
        # Wraps api providing the connection parameters.
        # The provided connection is the client current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if connection exists before invoking %s", api.__name__)

        sharing_conn, server_conn = \
            client._get_current_sharing_connection_or_create_from_sharing_location_args(args, ftype)

        # Server connection must be valid
        if not server_conn or not server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Sharing connection must be invalid, if ftype is FILE
        if ftype == FTYPE_DIR and (not sharing_conn or not sharing_conn.is_connected()):
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.d("Connection established, invoking %s", api.__name__)
        api(client, args, server_conn, sharing_conn, **kwargs)

        if sharing_conn != client.sharing_connection:
            log.d("Closing temporary sharing connection")
            sharing_conn.close()

        if server_conn != client.server_connection:
            log.d("Closing temporary server connection")
            server_conn.disconnect()

    wrapper.__name__ = api.__name__

    return wrapper


def provide_d_sharing_connection(api):
    return make_sharing_connection_api_wrapper(api, ftype=FTYPE_DIR)


def provide_sharing_connection(api):
    return make_sharing_connection_api_wrapper(api, ftype=None)


def make_server_connection_api_wrapper(api, connect: bool):
    def wrapper(client: 'Client', args: Args, _1: ServerConnection, _2: SharingConnection):
        # Wraps api providing the connection parameters.
        # The provided connection is the client current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if server connection exists before invoking %s", api.__name__)

        server_conn = client._get_current_server_connection_or_create_from_server_location_args(
            args,
            connect=connect
        )

        if not server_conn:
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.d("Server connection established, invoking '%s'", api.__name__)
        api(client, args, server_conn, None)

        if connect:
            if server_conn != client.server_connection:
                log.d("Disconnecting temporary server connection")
                server_conn.disconnect()
            # we have used our current server connection; don't disconnect it
        else:
            log.d("Server connection doesn't need to be disconnect()ed since connect=False")

    wrapper.__name__ = api.__name__

    return wrapper

def provide_server_connection_connected(api):
    return make_server_connection_api_wrapper(api, connect=True)

def provide_server_connection(api):
    return make_server_connection_api_wrapper(api, connect=False)

# ==================================================================

class CommandExecutionError(Exception):
    def __init__(self, errors: Union[int, str, List[str]] = ClientErrors.ERR_0):
        self.errors = errors

class HandledKeyboardInterrupt(KeyboardInterrupt):
    pass

# ==================================================================


class Client:

    def __init__(self, discover_port: int, discover_timeout: int):
        # self.connection: Optional[Connection] = None
        self.server_connection: Optional[ServerConnection] = None
        self.sharing_connection: Optional[SharingConnection] = None

        self._discover_port = discover_port
        self._discover_timeout = discover_timeout


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
                Callable[[Args, Optional[ServerConnection], Optional[SharingConnection]], None]
            ]
        ] = {

            Commands.LOCAL_CHANGE_DIRECTORY: (
                LOCAL,
                [PosArgsSpec(0, 1)],
                Client.cd),
            Commands.LOCAL_LIST_DIRECTORY: (
                LOCAL,
                [Ls(0)],
                Client.ls),
            Commands.LOCAL_LIST_DIRECTORY_ENHANCED: (
                LOCAL,
                [PosArgsSpec(0, 1)],
                Client.l),
            Commands.LOCAL_TREE_DIRECTORY: (
                LOCAL,
                [Tree(0)],
                Client.tree),
            Commands.LOCAL_CREATE_DIRECTORY: (
                LOCAL,
                [PosArgsSpec(1)],
                Client.mkdir),
            Commands.LOCAL_CURRENT_DIRECTORY: (
                LOCAL,
                [PosArgsSpec(0)],
                Client.pwd),
            Commands.LOCAL_REMOVE: (
                LOCAL,
                [VarArgsSpec(1)],
                Client.rm),
            Commands.LOCAL_MOVE: (
                LOCAL,
                [VarArgsSpec(2)],
                Client.mv),
            Commands.LOCAL_COPY: (
                LOCAL,
                [VarArgsSpec(2)],
                Client.cp),
            Commands.LOCAL_EXEC: (
                LOCAL,
                [StopParseArgsSpec(0)],
                Client.exec),
            Commands.LOCAL_SHELL: (
                LOCAL,
                [PosArgsSpec(0)],
                Client.shell),
            Commands.LOCAL_SHELL_SHORT: (
                LOCAL,
                [PosArgsSpec(0)],
                Client.shell),

            Commands.REMOTE_CHANGE_DIRECTORY: (
                SHARING,
                [PosArgsSpec(0, 1), PosArgsSpec(1, 1)],
                self.rcd),
            Commands.REMOTE_LIST_DIRECTORY: (
                SHARING,
                [Ls(0), Ls(1)],
                self.rls),
            Commands.REMOTE_LIST_DIRECTORY_ENHANCED: (
                SHARING,
                [PosArgsSpec(0, 1), PosArgsSpec(1, 1)],
                self.rl),
            Commands.REMOTE_TREE_DIRECTORY: (
                SHARING,
                [Tree(0), Tree(1)],
                self.rtree),
            Commands.REMOTE_CREATE_DIRECTORY: (
                SHARING,
                [PosArgsSpec(1), PosArgsSpec(2)],
                self.rmkdir),
            Commands.REMOTE_CURRENT_DIRECTORY: (
                SHARING,
                [PosArgsSpec(0), PosArgsSpec(1)],
                self.rpwd),
            Commands.REMOTE_REMOVE: (
                SHARING,
                [VarArgsSpec(1), VarArgsSpec(2)],
                self.rrm),
            Commands.REMOTE_MOVE: (
                SHARING,
                [VarArgsSpec(2), VarArgsSpec(3)],
                self.rmv),
            Commands.REMOTE_COPY: (
                SHARING,
                [VarArgsSpec(2), VarArgsSpec(3)],
                self.rcp),
            Commands.REMOTE_EXEC: (
                SERVER,
                [StopParseArgsSpec(0), StopParseArgsSpec(1)],
                self.rexec),
            Commands.REMOTE_SHELL: (
                SERVER,
                [PosArgsSpec(0), PosArgsSpec(1)],
                self.rshell),
            Commands.REMOTE_SHELL_SHORT: (
                SERVER,
                [PosArgsSpec(0), PosArgsSpec(1)],
                self.rshell),

            Commands.GET: (
                SHARING,
                [Get(0), Get(1)],
                self.get),

            Commands.PUT: (
                SHARING,
                [Put(0), Put(1)],
                self.put),


            Commands.SCAN: (
                LOCAL,
                [Scan()],
                self.scan),

            Commands.INFO: (
                SERVER,
                [PosArgsSpec(0, 1), PosArgsSpec(1, 0)],
                self.info),

            Commands.LIST: (
                SERVER,
                [ListSharings(0), ListSharings(1)],
                self.list),

            Commands.CONNECT: (
                SERVER,
                [PosArgsSpec(1), PosArgsSpec(1)],
                self.connect),
            Commands.DISCONNECT: (
                SERVER,
                [PosArgsSpec(0), PosArgsSpec(1)],
                self.disconnect),

            Commands.OPEN: (
                SERVER,
                [PosArgsSpec(1), PosArgsSpec(1)],
                self.open),
            Commands.CLOSE: (
                SHARING,
                [PosArgsSpec(0), PosArgsSpec(1)],
                self.close),

            Commands.PING: (
                SERVER,
                [Ping(0), Ping(1)],
                self.ping),
        }

        self._command_dispatcher[Commands.GET_SHORT] = self._command_dispatcher[Commands.GET]
        self._command_dispatcher[Commands.PUT_SHORT] = self._command_dispatcher[Commands.PUT]
        self._command_dispatcher[Commands.OPEN_SHORT] = self._command_dispatcher[Commands.OPEN]
        self._command_dispatcher[Commands.CLOSE_SHORT] = self._command_dispatcher[Commands.CLOSE]
        self._command_dispatcher[Commands.SCAN_SHORT] = self._command_dispatcher[Commands.SCAN]
        self._command_dispatcher[Commands.INFO_SHORT] = self._command_dispatcher[Commands.INFO]
        self._command_dispatcher[Commands.LOCAL_EXEC_SHORT] = self._command_dispatcher[Commands.LOCAL_EXEC]
        self._command_dispatcher[Commands.REMOTE_EXEC_SHORT] = self._command_dispatcher[Commands.REMOTE_EXEC]

    def has_command(self, command: str) -> bool:
        return command in self._command_dispatcher or \
               is_special_command(command)

    def execute_command(self, command: str, command_args: List[str]) -> Union[int, str, List[str]]:
        if not self.has_command(command):
            return ClientErrors.COMMAND_NOT_RECOGNIZED

        command_args_normalized = command_args.copy()

        # Handle special Commands (':')
        command_parts = command.rsplit(SPECIAL_COMMAND_MARK, maxsplit=1)
        if len(command_parts) > 1:
            command = command_parts[0] + SPECIAL_COMMAND_MARK
            log.d("Found special command: '%s'", command)
            if command_parts[1]:
                command_args_normalized.insert(0, command_parts[1])

        log.i("Executing %s(%s)", command, command_args_normalized)

        # Check which parser to use
        # The local Commands and the connected remote Commands use
        # the same parsers, while the unconnected remote Commands
        # need one more leading parameter (the remote sharing location)
        parser_provider, parser_provider_args, executor = self._command_dispatcher[command]

        parser = parser_provider(*parser_provider_args)

        # Parse args using the parsed bound to the command
        try:
            args = parser.parse(command_args_normalized)
        except ArgsParseError as err:
            log.e("Command's arguments parse failed: %s", str(err))
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.i("Parsed command arguments\n%s", args)

        try:
            executor(args, None, None)
            return 0

        except PyroError:
            # Pyro fail: destroy connection
            log.exception("Pyro exception caught, destroying active connections...")
            self.destroy_connection()
            return ClientErrors.CONNECTION_ERROR

        except CommandExecutionError as ex:
            # "Expected" fail
            err = ex.errors if ex.errors else ClientErrors.COMMAND_EXECUTION_FAILED
            log.exception("CommandExecutionError: %s", err)
            return err

        except Exception as ex:
            # Every other unexpected fail: destroy connection
            log.exception("Exception caught while executing command\n%s", ex)
            self.destroy_connection()
            return ClientErrors.COMMAND_EXECUTION_FAILED

    def is_connected_to_server(self) -> bool:
        return True if self.server_connection and \
                       self.server_connection.is_connected() else False

    def is_connected_to_sharing(self) -> bool:
        return True if self.sharing_connection and \
                       self.sharing_connection.is_connected() else False


    def destroy_connection(self):
        """ Destroy an eventual established server connection (and thus sharing conn) """
        try:
            log.d("Destroying connection and invalidating it")
            if self.is_connected_to_server():
                self.server_connection.disconnect()
            # Server closes the sharing by itself
            # There's no need to close() the sharing connection
        except:
            log.w("Clean disconnection failed, invalidating connection anyway")
        finally:
            self.server_connection = None
            self.sharing_connection = None

    # === LOCAL Commands ===

    @staticmethod
    def cd(args: Args, _, _2):
        directory = LocalPath(args.get_positional(), default="~")
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


    @staticmethod
    def pwd(_: Args, _2, _3):
        log.i(">> PWD")

        print(Path.cwd())

    @staticmethod
    def ls(args: Args, _, _2):

        def ls_provider(path: str, **kwargs):
            p = LocalPath(path)
            kws = {k: v for k, v in kwargs.items() if k in
                   ["sort_by", "name", "reverse", "hidden"]}
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

        Client._xls(args, ls_provider, "LS")

    @staticmethod
    def l(args: Args, _, _2):
        # Just call ls -la
        # Reuse the parsed args for keep the (optional) path
        args._parsed[Ls.SHOW_ALL[0]] = True
        args._parsed[Ls.SHOW_DETAILS[0]] = True
        Client.ls(args, _, _2)

    @staticmethod
    def tree(args: Args, _, _2):

        def tree_provider(path, **kwargs):
            p = LocalPath(path)
            kws = {k: v for k, v in kwargs.items() if k in
                   ["sort_by", "name", "reverse", "max_depth", "hidden"]}
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

        Client._xtree(args, tree_provider, "TREE")

    @staticmethod
    def mkdir(args: Args, _, _2):
        directory = args.get_positional()

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

    @staticmethod
    def rm(args: Args, _, _2):
        paths = [LocalPath(p) for p in args.get_positionals()]

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RM %s", paths)

        errors = []

        def handle_rm_error(exc: Exception, path):

            if isinstance(exc, PermissionError):
                errors.append(errno_str(ClientErrors.RM_PERMISSION_DENIED,
                                        q(path)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(errno_str(ClientErrors.RM_NOT_EXISTS,
                                        q(path)))
            elif isinstance(exc, OSError):
                errors.append(errno_str(ClientErrors.RM_OTHER_ERROR,
                                        os_error_str(exc),
                                        q(path)))
            else:
                errors.append(errno_str(ClientErrors.RM_OTHER_ERROR,
                                        exc,
                                        q(path)))

        for p in paths:
            rm(p, error_callback=handle_rm_error)

        if errors:
            raise CommandExecutionError(errors)



    @staticmethod
    def mv(args: Args, _, _2):
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

        Client._mvcp(args, mv, "MV", error_callback=handle_mv_error)

        if errors:
            raise CommandExecutionError(errors)

    @staticmethod
    def cp(args: Args, _, _2):

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

        Client._mvcp(args, cp, "CP", error_callback=handle_cp_error)

        if errors:
            raise CommandExecutionError(errors)

    @staticmethod
    def exec(args: Args, _, _2):
        if not is_unix():
            log.w("exec not supported on this platform")
            raise CommandExecutionError(ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX)

        popen_args = args.get_unparsed_args(default=[])
        popen_cmd = " ".join(popen_args)

        log.i(">> >> EXEC %s", popen_cmd)

        retcode = run_attached(popen_cmd)
        if retcode != 0:
            log.w("Command failed with return code: %d", retcode)

    @staticmethod
    def shell(args: Args, _, _2):
        if not is_unix():
            log.w("shell not supported on this platform")
            raise CommandExecutionError(ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX)

        passwd: struct_passwd = get_passwd()

        log.i(f"{passwd.pw_uid} {passwd.pw_name} - shell: {passwd.pw_shell}")

        log.i(">> SH %s")
        retcode = pty_attached(passwd.pw_shell)
        if retcode != 0:
            log.w("Command failed with return code: %d", retcode)


    # =================================================
    # ================ SERVER Commands ================
    # =================================================


    def connect(self, args: Args, _1, _2):
        log.i(">> CONNECT")

        server_location = ServerLocation.parse(args.get_positional())

        # Just in case check whether we already connected to the right one
        if self.is_connected_to_server():
            if Client.server_info_satisfy_server_location(
                    self.server_connection.server_info,
                    server_location
            ):
                log.w("Current connection already satisfy server location constraints")
                return

        # Actually create the connection
        new_server_conn = self._create_server_connection_from_server_location(
            ServerLocation.parse(args.get_positional()),
            connect=True
        )

        if not new_server_conn or not new_server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.SERVER_NOT_FOUND)

        log.i("Server connection established")

        if self.is_connected_to_server():
            log.i("Disconnecting current server connection before set the new one")
            self.server_connection.disconnect()

        self.server_connection = new_server_conn


    @provide_server_connection_connected
    def disconnect(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn or not server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.i(">> DISCONNECT")

        server_conn.disconnect()

        # TODO: cleanup ?

    def open(self, args: Args, _1, _2):
        log.i(">> OPEN")

        new_server_conn: Optional[ServerConnection] = None
        new_sharing_conn: Optional[SharingConnection] = None

        # Check whether we are connected to a server which owns the
        # sharing we are looking for, otherwise performs a scan
        sharing_location = SharingLocation.parse(args.get_positional())

        if not sharing_location:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        if self.is_connected_to_server():
            new_server_conn = self.server_connection

            if Client.server_info_satisfy_sharing_location(
                    self.server_connection.server_info,
                    sharing_location
            ):
                # The sharing is among the sharings of this connection
                log.d("The sharing we are looking for is among the sharings"
                      " of the already established server connection")

                # Check whether we are already connected to it, just in case
                if self.is_connected_to_sharing() and \
                    self.sharing_connection.sharing_info.get("name") == sharing_location.name:
                    log.w("Current sharing connection already satisfy the sharing constraints")

                    # Connection might be down, at least try to ping the remote
                    ping_resp = None

                    try:
                        ping_resp = self.server_connection.ping()
                    except:
                        # Will handle an invalid response here below
                        pass

                    if is_data_response(ping_resp) and ping_resp.get("data") == "pong":
                        log.d("Received valid response from the server we are already connected to - OK")
                        return
                    else:
                        log.e("Current connection is broken; destroying it")
                        self.destroy_connection()
                else:
                    # Do an open() with this server connection
                    new_sharing_conn = Client.create_sharing_connection_from_server_connection(
                        self.server_connection,
                        sharing_name=sharing_location.name
                    )


        # Have we found the sharing yet or do we have to perform a scan?
        if not new_server_conn or not new_sharing_conn:
            # Performs a scan
            new_sharing_conn, new_server_conn = \
                self._create_sharing_connection_from_sharing_location(sharing_location)

        if not new_server_conn or not new_sharing_conn or \
            not new_server_conn.is_connected() or not new_sharing_conn.is_connected():
            log.e("Server or sharing connection establishment failed")
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Close current stuff (if the new connections are actually new)

        if new_sharing_conn != self.sharing_connection and self.is_connected_to_sharing():
            log.d("Closing current sharing connection before set the new one")
            self.sharing_connection.close()

        if new_server_conn != self.server_connection and self.is_connected_to_server():
            log.i("Closing current server connection before set the new one")
            self.server_connection.disconnect()


        log.i("Server and sharing connection established")
        self.sharing_connection = new_sharing_conn

        # Just mark that the server connection has been created due open()
        # so that for symmetry close() will do disconnect() too
        if new_server_conn != self.server_connection:
            setattr(new_server_conn, "created_with_open", True)

        self.server_connection = new_server_conn


    @provide_server_connection_connected
    def rexec(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn or not server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        popen_args = args.get_unparsed_args(default=[])
        popen_cmd = " ".join(popen_args)

        log.i(">> REXEC %s", popen_cmd)

        rexec_resp = server_conn.rexec(popen_cmd)
        ensure_data_response(rexec_resp)

        rexec_uid = rexec_resp.get("data")

        rexec_service_uri = pyro_uri(rexec_uid,
                                   server_conn.server_ip(),
                                   server_conn.server_port())

        log.d("Rexec handler URI: %s", rexec_uid)

        rexec_service: Union[TracedPyroProxy, IRexecService]

        with TracedPyroProxy(rexec_service_uri) as rexec_service:

            retcode = None

            # --- STDOUT RECEIVER ---

            def rexec_stdout_receiver():
                try:
                    rexec_polling_proxy: Union[TracedPyroProxy, IRexecService]

                    with TracedPyroProxy(rexec_service_uri) as rexec_polling_proxy:
                        nonlocal retcode

                        while retcode is None:
                            resp = rexec_polling_proxy.recv()
                            ensure_data_response(resp)

                            recv_data = resp.get("data")

                            # log.d("REXEC recv: %s", str(recv))
                            stdout = recv_data.get("stdout")
                            stderr = recv_data.get("stderr")
                            retcode = recv_data.get("retcode")

                            try:
                                for line in stdout:
                                    print(line, end="", flush=True)

                                for line in stderr:
                                    print(red(line), end="", flush=True)
                            except OSError as oserr:
                                # EWOULDBLOCK may arise something...
                                log.w("Ignoring OSerror: %s", str(oserr))

                        log.i("REXEC done (%d)", retcode)
                except KeyboardInterrupt:
                    log.d("rexec CTRL+C detected on stdout thread, ignoring")
                    retcode = -1
                except PyroError:
                    log.exception("Pyro error occurred on rexec stdout receiver thread")
                    retcode = -1
                except Exception:
                    log.exception("Unexpected error occurred on rexec stdout receiver thread")
                    retcode = -1


            rexec_stdout_receiver_th = threading.Thread(
                target=rexec_stdout_receiver, daemon=True)
            rexec_stdout_receiver_th.start()

            # --- STDIN SENDER ---

            # Put stdin in non-blocking mode

            stding_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
            fcntl.fcntl(sys.stdin, fcntl.F_SETFL, stding_flags | os.O_NONBLOCK)

            # try:
            while retcode is None:
                try:
                    # Do not block so that we can exit when the process
                    # finishes
                    rlist, wlist, xlist = select.select([sys.stdin], [], [], 0.04)

                    if sys.stdin in rlist:
                        data_b = sys.stdin.buffer.read()

                        if data_b:
                            data_s = bytes_to_str(data_b)
                            log.d("Sending data: %s", data_s)
                            rexec_service.send_data(data_s)
                        else:
                            log.d("rexec CTRL+D")
                            rexec_service.send_event(IRexecService.Event.EOF)
                except KeyboardInterrupt:
                    log.d("rexec CTRL+C")
                    rexec_service.send_event(IRexecService.Event.TERMINATE)
                    # Design choice: do not break here but wait that the remote
                    # notify us about the command completion

            # Restore stdin in blocking mode

            fcntl.fcntl(sys.stdin, fcntl.F_SETFL, stding_flags)

            # Wait everybody

            rexec_stdout_receiver_th.join()



    @provide_server_connection_connected
    def rshell(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn or not server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.i(">> RSHELL %s")

        rshell_resp = server_conn.rshell()
        ensure_data_response(rshell_resp)

        rshell_uid = rshell_resp.get("data")

        rshell_service_uri = pyro_uri(rshell_uid,
                                   server_conn.server_ip(),
                                   server_conn.server_port())

        log.d("Rshell handler URI: %s", rshell_uid)

        rshell_service: Union[TracedPyroProxy, IRshellService]

        with TracedPyroProxy(rshell_service_uri) as rshell_service:

            retcode = None

            # --- STDOUT RECEIVER ---

            def rshell_stdout_receiver():
                try:
                    rshell_polling_proxy: Union[TracedPyroProxy, IRshellService]

                    with TracedPyroProxy(rshell_service_uri) as rshell_polling_proxy:
                        nonlocal retcode

                        while retcode is None:
                            resp = rshell_polling_proxy.recv()
                            ensure_data_response(resp)

                            recv_data = resp.get("data")

                            log.d("REXEC recv: %s", str(recv_data))
                            out = recv_data.get("out")
                            retcode = recv_data.get("retcode")

                            try:
                                for content in out:
                                    if content:
                                        print(content, end="", flush=True)
                            except OSError as oserr:
                                # EWOULDBLOCK may arise something...
                                log.w("Ignoring OSerror: %s", str(oserr))

                        log.i("RSHELL done (%d)", retcode)
                except KeyboardInterrupt:
                    log.d("rshell CTRL+C detected on stdout thread, ignoring")
                    retcode = -1
                except PyroError:
                    log.exception("Pyro error occurred on rhsell out receiver thread")
                    retcode = -1
                except Exception:
                    log.exception("Unexpected error occurred on rshell out receiver thread")
                    retcode = -1


            rshell_stdout_receiver_th = threading.Thread(
                target=rshell_stdout_receiver, daemon=True)
            rshell_stdout_receiver_th.start()

            # --- STDIN SENDER ---

            # Put stdin in raw mode (read char by char)

            try:
                mode = tty.tcgetattr(pty.STDIN_FILENO)
                tty.setraw(pty.STDIN_FILENO)
                restore = 1
            except tty.error:  # This is the same as termios.error
                restore = 0
            try:
                while retcode is None:
                    try:
                        # Do not block so that we can exit when the process
                        # finishes
                        rlist, wlist, xlist = select.select([pty.STDIN_FILENO], [], [], 0.04)

                        if pty.STDIN_FILENO in rlist:
                            data_b = os.read(pty.STDIN_FILENO, 1024)
                            if data_b:
                                data_s = bytes_to_str(data_b)
                                log.d("Sending data: %s", repr(data_b))
                                rshell_service.send_data(data_s)
                            else:
                                log.d("rshell CTRL+D")
                                rshell_service.send_event(IRshellService.Event.EOF)
                    except KeyboardInterrupt:
                        log.d("rexec CTRL+C")
                        rshell_service.send_event(IRshellService.Event.TERMINATE)
                        # Design choice: do not break here but wait that the remote
                        # notify us about the command completion

            except OSError:
                log.exception("OSError")
            finally:
                # Restore stdin in blocking mode
                if restore:
                    tty.tcsetattr(pty.STDIN_FILENO, tty.TCSAFLUSH, mode)

            # Wait everybody
            rshell_stdout_receiver_th.join()

    @provide_server_connection
    def ping(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        count = args.get_option_param(Ping.COUNT, default=None)

        i = 1
        while not count or i <= count:
            timer = Timer(start=True)
            resp = server_conn.ping()
            timer.stop()

            if is_data_response(resp) and resp.get("data") == "pong":
                print("[{}] PONG from {}  |  time={:.1f}ms".format(
                    i,
                    server_info_to_short_str(server_conn.server_info),
                    timer.elapsed_ms())
                )
            else:
                print("[{}] FAIL")

            i += 1
            time.sleep(1)

    # =================================================
    # =============== PROBING Commands ================
    # =================================================

    def scan(self, args: Args, _, _2):

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
            else:
                s += "\n"

            s += bold("{}. {}".format(
                      servers_found + 1,
                      server_info_to_short_str(server_info_full)))

            if show_all_details:
                s += "\n" + server_info_to_pretty_str(server_info_full,
                                                      sharing_details=True) + "\n" + SEP
            else:
                sharings_str = sharings_to_pretty_str(
                    server_info_full.get("sharings"),
                    details=show_sharings_details,
                    indent=2)

                if sharings_str:
                    s +=  "\n" + sharings_str
                # else: NONE

            # DELETE_EOL for overwrite progress bar render

            print(ansi.DELETE_EOL + s, flush=True)

            servers_found += 1

            return True     # Continue DISCOVER

        self._discover(
            discover_port=self._discover_port,
            discover_timeout=self._discover_timeout,
            response_handler=response_handler,
            progress=True,
            success_if_ends=True
        )

        log.i("======================")

    @provide_server_connection
    def info(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        show_sharings_details = Info.SHOW_SHARINGS_DETAILS in args

        print(server_info_to_pretty_str(server_conn.server_info,
                                        sharing_details=show_sharings_details,
                                        separators=True))

    @provide_server_connection
    def list(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        show_details = ListSharings.SHOW_DETAILS in args

        log.i(">> LIST")

        resp = server_conn.list()
        ensure_data_response(resp)

        sharings_str = sharings_to_pretty_str(resp.get("data"),
                                     details=show_details)

        if sharings_str:
            print(sharings_str)
        else:
            log.w("Remote server doesn't have any sharing")


    # =================================================
    # ================ SHARING Commands ===============
    # =================================================

    @provide_d_sharing_connection
    def close(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.i(">> CLOSE")

        sharing_conn.close()

        # noinspection PyUnresolvedReferences
        if server_conn and server_conn.is_connected() and \
                getattr(server_conn, "created_with_open", False):
            log.d("Closing server connection too since opened due open")
            server_conn.disconnect()


    @provide_d_sharing_connection
    def rpwd(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        log.i(">> RPWD")
        resp = sharing_conn.rpwd()
        ensure_data_response(resp)

        rcwd = resp.get("data")

        print(Path("/").joinpath(rcwd))

    @provide_d_sharing_connection
    def rcd(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        directory = args.get_positional(default="/")

        log.i(">> RCD %s", directory)

        resp = sharing_conn.rcd(directory)
        ensure_data_response(resp)

        log.d("Current rcwd: %s", sharing_conn.rcwd())

    @provide_d_sharing_connection
    def rls(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        def rls_provider(f, **kwargs):
            resp = sharing_conn.rls(**kwargs, path=f)
            ensure_data_response(resp)
            return resp.get("data")

        Client._xls(args, data_provider=rls_provider, data_provider_name="RLS")

    def rl(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        # Just call rls -la
        # Reuse the parsed args for keep the (optional) path
        args._parsed[Ls.SHOW_ALL[0]] = True
        args._parsed[Ls.SHOW_DETAILS[0]] = True
        self.rls(args, server_conn, sharing_conn)

    @provide_d_sharing_connection
    def rtree(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        def rtree_provider(f, **kwargs):
            resp = sharing_conn.rtree(**kwargs, path=f)
            ensure_data_response(resp)
            return resp.get("data")

        Client._xtree(args, data_provider=rtree_provider, data_provider_name="RTREE")

    @provide_d_sharing_connection
    def rmkdir(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        directory = args.get_positional()

        if not directory:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RMKDIR %s", directory)

        resp = sharing_conn.rmkdir(directory)
        ensure_success_response(resp)

    @provide_d_sharing_connection
    def rrm(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        paths = args.get_positionals()

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RRM %s ", paths)

        resp = sharing_conn.rrm(paths)
        ensure_success_response(resp)

    @provide_d_sharing_connection
    def rmv(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        Client._rmvcp(args, api=sharing_conn.rmv, api_name="RMV")

    @provide_d_sharing_connection
    def rcp(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        Client._rmvcp(args, api=sharing_conn.rcp, api_name="RCP")

    @provide_sharing_connection
    def get(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        files = args.get_positionals()

        do_check = Put.CHECK in args
        quiet = Put.QUIET in args

        resp = sharing_conn.get(files, check=do_check)
        ensure_data_response(resp, "uid")

        # Compute the remote daemon URI from the uid of the get() response
        get_service_uri = pyro_uri(resp.get("data").get("uid"),
                                   server_conn.server_ip(),
                                   server_conn.server_port())
        log.d("Remote GetService URI: %s", get_service_uri)

        # Raw transfer socket
        try:
            transfer_socket = SocketTcpOut(
                address=sharing_conn.server_info.get("ip"),
                port=transfer_port(sharing_conn.server_info.get("port")),
                ssl_context=get_ssl_context(),
                timeout=self._discover_timeout  # well it's not a discovery,
                                                # but at least should be a
                                                # timeout that make sense
            )
        except ConnectionRefusedError:
            log.exception("Transfer socket creation failed (closed)")
            raise CommandExecutionError("Transfer connection can't be established: refused")
        except socket.timeout:
            log.exception("Transfer socket creation failed (timeout)")
            raise CommandExecutionError("Transfer connection can't be established: timed out")
        except OSError as oserr:
            log.exception("Transfer socket creation failed")
            raise CommandExecutionError(os_error_str(oserr))
        except Exception as exc:
            log.exception("Transfer socket creation failed")
            raise CommandExecutionError(str(exc))

        # Overwrite preference

        if [Get.OVERWRITE_YES in args, Get.OVERWRITE_NO in args,
            Get.OVERWRITE_NEWER].count(True) > 1:
            log.e("Only one between -n, -y and -N can be specified")
            raise CommandExecutionError("Only one between -n, -y and -N can be specified")

        overwrite_policy = OverwritePolicy.PROMPT

        if Get.OVERWRITE_YES in args:
            overwrite_policy = OverwritePolicy.YES
        elif Get.OVERWRITE_NO in args:
            overwrite_policy = OverwritePolicy.NO
        elif Get.OVERWRITE_NEWER in args:
            overwrite_policy = OverwritePolicy.NEWER

        log.i("Overwrite policy: %s", str(overwrite_policy))

        # Stats

        progressor = None

        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Errors

        errors = []

        # Proxy

        get_service: Union[TracedPyroProxy, IGetService]

        with TracedPyroProxy(get_service_uri) as get_service:

            while True:
                log.i("Fetching another file info")
                # The first next() fetch never implies a new file to be put
                # on the transfer socket.
                # We have to check whether we want to eventually overwrite
                # the file, and then tell the server next() if
                # 1. Really transfer the file
                # 2. Skip the file

                will_transfer = overwrite_policy == OverwritePolicy.NO
                will_seek = not will_transfer

                log.i("Action: %s", "transfer" if will_transfer else "seek")
                get_next_resp = get_service.next(
                    # Transfer immediately since we won't ask to the user
                    # whether overwrite or not
                    transfer=will_transfer
                )

                ensure_success_response(get_next_resp)  # it might be without data

                next_file: FileInfo = get_next_resp.get("data")

                if not next_file:
                    log.i("Nothing more to GET")
                    break

                fname = next_file.get("name")
                fsize = next_file.get("size")
                ftype = next_file.get("ftype")
                fmtime = next_file.get("mtime")

                local_path = Path(fname)

                log.i("NEXT: %s of type %s", fname, ftype)

                # Case: DIR
                if ftype == FTYPE_DIR:
                    log.i("Creating dirs %s", fname)
                    local_path.mkdir(parents=True, exist_ok=True)
                    continue  # No FTYPE_FILE => neither skip nor transfer for next()

                if ftype != FTYPE_FILE:
                    log.w("Cannot handle this ftype")
                    continue  # No FTYPE_FILE => neither skip nor transfer for next()

                # Case: FILE
                local_path_parent = local_path.parent
                if local_path_parent:
                    log.i("Creating parent dirs %s", local_path_parent)
                    local_path_parent.mkdir(parents=True, exist_ok=True)

                # Check whether it already exists
                if local_path.is_file():
                    log.w("File already exists, asking whether overwrite it (if needed)")

                    # Overwrite handling

                    timer.stop() # Don't take the user time into account
                    current_overwrite_decision, overwrite_policy = \
                        self._ask_overwrite(fname, current_policy=overwrite_policy)
                    timer.start()

                    log.d("Overwrite decision: %s", str(current_overwrite_decision))

                    if will_seek:
                        do_skip = False

                        if current_overwrite_decision == OverwritePolicy.NO:
                            # Skip
                            do_skip = True
                        elif current_overwrite_decision == OverwritePolicy.NEWER:
                            # Check whether skip or not based on the last modified time
                            log.d("Checking whether skip based on mtime")
                            stat = local_path.stat()
                            do_skip = stat.st_mtime_ns >= fmtime
                            log.d("Local mtime: %d | Remote mtime: %d => skip: %s",
                                  stat.st_mtime_ns, fmtime, do_skip)

                        if do_skip:
                            log.d("Would have seek, have to tell server to skip %s", fname)
                            get_next_resp = get_service.next(skip=True)
                            ensure_success_response(get_next_resp)
                            continue
                        else:
                            log.d("Not skipping")


                # Eventually tell the server to begin the transfer
                # We have to call it now because the server can't know
                # in advance if we want or not overwrite the file
                if will_seek:
                    log.d("Would have seek, have to tell server to transfer %s", fname)
                    get_next_resp = get_service.next(transfer=True)

                    # The server may say the transfer can't be done actually (e.g. EPERM)
                    if is_success_response(get_next_resp):
                        log.d("Transfer can actually began")
                    elif is_error_response(get_next_resp):
                        log.w("Transfer cannot be initialized due to remote error")

                        errors += get_next_resp.get("errors")

                        # All the errors will be reported at the end
                        continue
                    else:
                        raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

                # else: file already put into the transer socket

                if not quiet:
                    progressor = FileProgressor(
                        fsize,
                        description="GET " + fname,
                        color_progress=PROGRESS_COLOR,
                        color_success=SUCCESS_COLOR,
                        color_error=ERROR_COLOR
                    )

                log.i("Opening %s locally", fname)
                f = local_path.open("wb")

                cur_pos = 0
                expected_crc = 0

                while cur_pos < fsize:
                    recv_size = min(BEST_BUFFER_SIZE, fsize - cur_pos)
                    log.i("Waiting chunk... (expected size: %dB)", recv_size)

                    chunk = transfer_socket.recv(recv_size)

                    if not chunk:
                        log.i("END")
                        raise CommandExecutionError()

                    chunk_len = len(chunk)

                    log.i("Received chunk of %dB", chunk_len)

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


                log.i("DONE %s", fname)
                log.d("- crc = %d", expected_crc)

                f.close()

                # Eventually do CRC check
                if do_check:
                    # CRC check on the received bytes
                    crc = bytes_to_int(transfer_socket.recv(4))
                    if expected_crc != crc:
                        log.e("Wrong CRC; transfer failed. expected=%d | written=%d",
                              expected_crc, crc)
                        return # Really don't know how to recover from this disaster
                    else:
                        log.d("CRC check: OK")

                    # Length check on the written file
                    written_size = local_path.stat().st_size
                    if written_size != fsize:
                        log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                              fsize, written_size)
                        return # Really don't know how to recover from this disaster
                    else:
                        log.d("File length check: OK")

                n_files += 1
                if not quiet:
                    progressor.success()

            # Wait for completion
            outcome_resp = get_service.outcome()
            ensure_data_response(outcome_resp, "outcome")

            timer.stop()
            elapsed_s = timer.elapsed_s()

            transfer_socket.close()

            # Take outcome and (eventually) errors out of the resp
            outcome = outcome_resp.get("data").get("outcome")
            outcome_errors = outcome_resp.get("data").get("errors")
            if outcome_errors:
                log.w("Response has errors")
                errors += outcome_errors

            log.i("GET outcome: %d", outcome)

            print("")
            print("GET outcome:  {}".format(outcome_str(outcome)))
            print("-----------------------")
            print("Files:        {} ({})".format(n_files, size_str(tot_bytes)))
            print("Time:         {}".format(duration_str_human(round(elapsed_s))))
            print("Avg. speed:   {}".format(speed_str(tot_bytes / elapsed_s)))

            # Any error? (e.g. permission denied)
            if errors:
                print("-----------------------")
                print("Errors:       {}".format(len(errors)))
                for idx, err in enumerate(errors):
                    err_str = formatted_error_from_error_of_response(err)
                    print(f"{idx + 1}. {err_str}")

    @provide_d_sharing_connection
    def put(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):

        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        files = args.get_positionals()
        sendfiles: List[Tuple[Path, Path]] = []

        if len(files) == 0:
            files = ["."]

        do_check = Put.CHECK in args
        quiet = Put.QUIET in args

        resp = sharing_conn.put(check=do_check)
        ensure_data_response(resp, "uid")

        # Compute the remote daemon URI from the uid of the get() response
        put_service_uri = pyro_uri(resp.get("data").get("uid"),
                                   server_conn.server_ip(),
                                   server_conn.server_port())
        log.d("Remote PutService URI: %s", put_service_uri)

        # Raw transfer socket
        try:
            transfer_socket = SocketTcpOut(
                address=sharing_conn.server_info.get("ip"),
                port=transfer_port(sharing_conn.server_info.get("port")),
                ssl_context=get_ssl_context(),
                timeout=self._discover_timeout  # well it's not a discovery,
                                                # but at least should be a
                                                # timeout that make sense
            )
        except ConnectionRefusedError:
            log.exception("Transfer socket creation failed (closed)")
            raise CommandExecutionError("Transfer connection can't be established: refused")
        except socket.timeout:
            log.exception("Transfer socket creation failed (timeout)")
            raise CommandExecutionError("Transfer connection can't be established: timed out")
        except OSError as oserr:
            log.exception("Transfer socket creation failed")
            raise CommandExecutionError(os_error_str(oserr))
        except Exception as exc:
            log.exception("Transfer socket creation failed")
            raise CommandExecutionError(str(exc))

        for f in files:
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
            log.d("f = %s", f)

            p = LocalPath(f)

            take_all_unwrapped = True if (p.parts and p.parts[len(p.parts) - 1]) == "*" else False

            log.d("is * = %s", take_all_unwrapped)

            if take_all_unwrapped:
                # Consider the path without the last *
                p = p.parent


            log.d("p(f) = %s", p)
            fpath = p.resolve()

            log.d("fpath(f) = %s", fpath)

            if take_all_unwrapped:
                rpath = Path("")
            else:
                rpath = Path(fpath.name)

            log.d("rpath(f) = %s", rpath)

            sendfile = (fpath, rpath)
            log.i("Adding sendfile %s", sendfile)
            sendfiles.append(sendfile)

        # Overwrite preference

        if [Get.OVERWRITE_YES in args, Get.OVERWRITE_NO in args,
            Get.OVERWRITE_NEWER].count(True) > 1:
            log.e("Only one between -n, -y and -N can be specified")
            raise CommandExecutionError("Only one between -n, -y and -N can be specified")

        overwrite_policy = OverwritePolicy.PROMPT

        if Put.OVERWRITE_YES in args:
            overwrite_policy = OverwritePolicy.YES
        elif Put.OVERWRITE_NO in args:
            overwrite_policy = OverwritePolicy.NO
        elif Put.OVERWRITE_NEWER in args:
            overwrite_policy = OverwritePolicy.NEWER

        log.i("Overwrite policy: %s", str(overwrite_policy))

        # Stats

        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Errors

        errors = []

        # Proxy

        put_service: Union[TracedPyroProxy, IPutService]

        with TracedPyroProxy(put_service_uri) as put_service:

            def send_file(local_path: Path, remote_path: Path):
                nonlocal overwrite_policy
                nonlocal tot_bytes
                nonlocal n_files
                nonlocal errors

                progressor = None

                # Create the file info for the local file, but set the
                # remote path as name
                finfo = create_file_info(local_path, name=str(remote_path))
                log.i("send_file finfo: %s", j(finfo))
                fsize = finfo.get("size")
                ftype = finfo.get("ftype")

                # Case: DIR => no transfer
                if ftype == FTYPE_DIR:
                    log.d("Sent a DIR, nothing else to do")
                    return

                # Case: FILE => transfer

                # Before invoke next(), try to open the file for real.
                # At least we are able to detect any error (e.g. perm denied)
                # before say the server that the transfer is began
                log.d("Trying to open file before initializing transfer")

                try:
                    local_fd = local_path.open("rb")
                    log.d("Able to open file: %s", local_path)
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

                put_next_resp = put_service.next(finfo, overwrite_policy=overwrite_policy)
                ensure_data_response(put_next_resp)

                if is_error_response(put_next_resp):
                    log.w("Received error response for next()")
                    errors += put_next_resp.get("errors")
                    # All the errors will be reported at the end
                    return

                if not is_data_response(put_next_resp):
                    raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

                # Possible responses:
                # "accepted" => add the file to the transfer socket
                # "refused"  => do not add the file to the transfer socket
                # "ask_overwrite" => ask to the user and tell it to the esd
                #                    we got this response only if the overwrite
                #                    policy told to the server is PROMPT

                # First of all handle the ask_overwrite, and contact the esd
                # again for tell the response
                if put_next_resp.get("data") == PutNextResponse.ASK_OVERWRITE:
                    # Ask the user what to do

                    timer.stop() # Don't take the user time into account
                    current_overwrite_decision, overwrite_policy =\
                        self._ask_overwrite(str(remote_path), current_policy=overwrite_policy)
                    timer.start()

                    if current_overwrite_decision == OverwritePolicy.NO:
                        log.i("Skipping %s", remote_path)
                        return

                    # If overwrite policy is NEWER or YES we have to tell it
                    # to the server so that it will take the right action
                    put_next_resp = put_service.next(finfo,
                                                     overwrite_policy=current_overwrite_decision)

                    if is_success_response(put_next_resp):
                        log.d("Transfer can actually began")
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
                if put_next_resp.get("data") == PutNextResponse.REFUSED:
                    log.i("Skipping %s ", remote_path)
                    return

                if put_next_resp.get("data") != PutNextResponse.ACCEPTED:
                    raise CommandExecutionError(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

                # File has been accepted by the remote, we can begin the transfer

                if not quiet:
                    progressor = FileProgressor(
                        fsize,
                        description="PUT " + str(remote_path),
                        color_progress=PROGRESS_COLOR,
                        color_success=SUCCESS_COLOR,
                        color_error=ERROR_COLOR
                    )

                # File is already opened

                cur_pos = 0
                crc = 0

                while cur_pos < fsize:

                    chunk = local_fd.read(BEST_BUFFER_SIZE)
                    chunk_len = len(chunk)

                    log.i("Read chunk of %dB", chunk_len)

                    # CRC check update
                    if do_check:
                        crc = zlib.crc32(chunk, crc)

                    if not chunk:
                        log.i("Finished %s", local_path)
                        # FIXME: sending something?
                        break

                    transfer_socket.send(chunk)

                    cur_pos += chunk_len
                    tot_bytes += chunk_len
                    if not quiet:
                        progressor.update(cur_pos)

                log.i("DONE %s", local_path)
                log.d("- crc = %d", crc)

                if do_check:
                    transfer_socket.send(int_to_bytes(crc, 4))

                local_fd.close()

                n_files += 1
                if not quiet:
                    progressor.success()


            while sendfiles:
                log.i("Putting another file info")
                next_file = sendfiles.pop()

                # Check what is this
                # 1. Non existing: skip
                # 2. A file: send it directly (parent dirs won't be replicated)
                # 3. A dir: send it recursively
                next_file_local, next_file_remote = next_file

                if next_file_local.is_file():
                    # Send it directly
                    log.d("-> is a FILE")
                    send_file(next_file_local, next_file_remote)
                elif next_file_local.is_dir():
                    # Send it recursively

                    log.d("-> is a DIR")

                    try:
                        dir_files: List[Path] = list(next_file_local.iterdir())
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

                    if dir_files:

                        log.i("Found a filled directory: adding all inner files to remaining_files")
                        for file_in_dir in dir_files:
                            sendfile = (file_in_dir, next_file_remote / file_in_dir.name)
                            log.i("Adding sendfile %s", sendfile)
                            sendfiles.append(sendfile)
                    else:
                        log.i("Found an empty directory")
                        log.d("Pushing an info for the empty directory")

                        send_file(next_file_local, next_file_remote)
                else:
                    log.w(f"Failed to send '{next_file_local}': unknown file type, doing nothing")

            log.i("Sending DONE")

            put_next_end_resp = put_service.next(None)
            ensure_success_response(put_next_end_resp)

            # Wait for completion
            outcome_resp = put_service.outcome()
            ensure_data_response(outcome_resp, "outcome")

            timer.stop()
            elapsed_s = timer.elapsed_s()

            transfer_socket.close()

            # Take outcome and (eventually) errors out of the resp
            outcome = outcome_resp.get("data").get("outcome")
            outcome_errors = outcome_resp.get("data").get("errors")
            if outcome_errors:
                log.w("Response has errors")
                errors += outcome_errors

            log.i("PUT outcome: %d", outcome)

            print("")
            print("PUT outcome:  {}".format(outcome_str(outcome)))
            print("-----------------------")
            print("Files:        {} ({})".format(n_files, size_str(tot_bytes)))
            print("Time:         {}".format(duration_str_human(round(elapsed_s))))
            print("Avg. speed:   {}".format(speed_str(tot_bytes / elapsed_s)))

            # Any error? (e.g. permission denied)
            if errors:
                print("-----------------------")
                print("Errors:       {}".format(len(errors)))
                for idx, err in enumerate(errors):
                    err_str = formatted_error_from_error_of_response(err)
                    print(f"{idx + 1}. {err_str}")

    @staticmethod
    def _xls(args: Args,
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

        log.i(">> %s %s (sort by %s%s)",
              data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")

        ls_result = data_provider(path, sort_by=sort_by, reverse=reverse, hidden=show_hidden)

        if ls_result is None:
            raise CommandExecutionError()

        print_files_info_list(
            ls_result,
            show_file_type=Ls.SHOW_DETAILS in args,
            show_hidden=show_hidden,
            show_size=Ls.SHOW_SIZE in args or Ls.SHOW_DETAILS in args,
            compact=Ls.SHOW_DETAILS not in args
        )

    @staticmethod
    def _xtree(args: Args,
               data_provider: Callable[..., Optional[FileInfoTreeNode]],
               data_provider_name: str = "TREE"):

        path = args.get_positional()
        reverse = Tree.REVERSE in args
        show_hidden = Tree.SHOW_ALL in args
        max_depth = args.get_option_param(Tree.MAX_DEPTH, default=None)

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
            hidden=show_hidden, max_depth=max_depth
        )

        if tree_result is None:
            raise CommandExecutionError()

        print_files_info_tree(tree_result,
                              max_depth=max_depth,
                              show_hidden=show_hidden,
                              show_size=Tree.SHOW_SIZE in args or Tree.SHOW_DETAILS in args)

    @staticmethod
    def _mvcp(args: Args,
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


        mvcp_args = [LocalPath(f) for f in args.get_positionals()]

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


    @staticmethod
    def _rmvcp(args: Args,
               api: Callable[[List[str], str], Response],
               api_name: str = "RMV/RCP"):
        paths = args.get_positionals()

        if not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        dest = paths.pop()

        if not dest or not paths:
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> %s %s -> %s", api_name, str(paths), dest)

        resp = api(paths, dest)
        ensure_success_response(resp)



    def _get_current_sharing_connection_or_create_from_sharing_location_args(
            self, args: Args, sharing_ftype: FileType) \
            -> Tuple[Optional[SharingConnection], ServerConnection]:
        """
        Returns the current sharing, server connection if already established.
        Otherwise tries to create a new one considering the first arg of 'args'
        as a sharing location (popping the arg).
        """

        if self.is_connected_to_server() and self.is_connected_to_sharing():
            log.i("Providing already established sharing connection")
            return self.sharing_connection, self.server_connection

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
            self, args: Args, connect: bool) -> ServerConnection:
        """
        Returns the current server connection if already established.
        Otherwise tries to create a new one considering the first arg of 'args'
        as a server location (popping the arg).
        """

        if self.is_connected_to_server():
            log.i("Providing already established server connection")
            return self.server_connection

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
            sharing_ftype: FileType = None,
    ) -> Tuple[Optional[SharingConnection], ServerConnection]:
        """
        Creates a new SharingConnection (and thus a ServerConnection)
        for the given sharing location.
        """

        server_conn = self._create_server_connection(
            connect=True,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=sharing_ftype,
        )

        if not server_conn or not server_conn.is_connected():
            raise CommandExecutionError(ClientErrors.INVALID_COMMAND_SYNTAX)

        sharing_conn = Client.create_sharing_connection_from_server_connection(
            server_conn=server_conn,
            sharing_name=sharing_location.name,
        )

        if not sharing_conn or not sharing_conn.is_connected():
            raise CommandExecutionError(ClientErrors.SHARING_NOT_FOUND)

        return sharing_conn, server_conn


    def _create_server_connection_from_server_location(
            self, server_location: ServerLocation, connect: bool) -> ServerConnection:
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
            sharing_name: str = None, sharing_ftype: FileType = None) -> ServerConnection:
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

                # Create a connection
                server_conn = ServerConnectionMinimal(
                    server_ip=server_ip,
                    server_port=attempt_port,
                    server_ssl=server_ssl
                )

                # Check if it is up
                # (e.g. if the port was not specified in case 2. maybe the user
                # want to perform a scan instead of connect to the default port,
                # by checking if the connection is up we are able to figure out that)

                try:
                    resp = server_conn.info()
                    ensure_data_response(resp)

                    real_server_info = resp.get("data")
                    log.d("Connection established is UP, retrieved server info\n%s",
                          j(real_server_info))

                    # Fill the uncomplete server info with the IP/port we used to connect
                    break
                except Exception:
                    log.w("Connection cannot be established directly %s SSL",
                          "with" if server_ssl else "without")
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


                if self.server_info_satisfy_constraints(
                        # DO not check server identity: this is needed for allow servers
                        # behind NAT to be reached without know the real internal IP/port
                        real_server_info,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND directly")
                    server_conn = ServerConnection(
                        server_ip=server_ip,
                        server_port=attempt_port,
                        server_info=real_server_info,
                        established_server_connection=server_conn.server
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

                if self.server_info_satisfy_constraints_full(
                        real_server_info,
                        server_name=server_name, server_ip=server_ip, server_port=server_port,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND w/ discover")
                    # IP and port can be provided from real_server_info
                    # since came from the discover and thus are real
                    server_conn = ServerConnection(
                        server_ip=real_server_info.get("ip"),
                        server_port=real_server_info.get("port"),
                        server_info=real_server_info
                    )

        if not server_conn:
            log.e("Connection can't be established")
            raise CommandExecutionError(ErrorsStrings.CONNECTION_CANT_BE_ESTABLISHED)

        # We have a valid TCP connection with the esd
        log.i("Connection established with %s:%d",
              server_conn.server_ip(),
              server_conn.server_port())

        # We have a valid TCP connection with the esd
        log.d("-> same as %s:%d",
              server_conn.server_info.get("ip"),
              server_conn.server_info.get("port"))

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

            if Client.server_info_satisfy_constraints_full(
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
            discover_port=self._discover_port,
            discover_addr=server_ip or ADDR_BROADCAST,
            discover_timeout=self._discover_timeout,
            response_handler=response_handler,
            progress=True,
            success_if_ends=False
        )

        return server_info

    @classmethod
    def create_sharing_connection_from_server_connection(cls,
            server_conn: ServerConnection, sharing_name: str) -> SharingConnection:
        """
        Given an already valid server connection, tries to establish a sharing
        connection to the sharing with the given name (=> does open())
        """

        if not server_conn:
            raise CommandExecutionError(ClientErrors.NOT_CONNECTED)

        # Create the sharing connection: open()

        open_resp = server_conn.open(sharing_name)
        ensure_data_response(open_resp)

        sharing_uid = open_resp.get("data")

        # Take out the sharing info from the server info
        for shinfo in server_conn.server_info.get("sharings"):
            if shinfo.get("name") == sharing_name:
                log.d("Found the sharing info among server_info sharings")

                sharing_conn = SharingConnection(
                    sharing_uid,
                    sharing_info=shinfo,
                    server_info=server_conn.server_info
                )

                return sharing_conn

        raise CommandExecutionError(ClientErrors.SHARING_NOT_FOUND)


    @classmethod
    def server_info_satisfy_server_location(cls,
            server_info: ServerInfo, server_location: ServerLocation):
        """ Whether 'server_info' satisfy 'server_location' """
        return cls.server_info_satisfy_constraints(
                server_info,
                server_name=server_location.name)

    @classmethod
    def server_info_satisfy_sharing_location(cls,
            server_info: ServerInfo, sharing_location: SharingLocation):
        """ Whether 'server_info' satisfy 'sharing_location' """

        return cls.server_info_satisfy_constraints(
                server_info,
                server_name=sharing_location.server_name,
                sharing_name=sharing_location.name,
                sharing_ftype=FTYPE_DIR)

    @classmethod
    def server_info_satisfy_constraints(cls,
            server_info: ServerInfo,
            server_name: str = None,
            sharing_name: str = None,
            sharing_ftype: FileType = None) -> bool:
        """ Whether 'server_info' satisfy the given filters """

        # Make a shallow copy
        server_info_full: ServerInfoFull = cast(ServerInfoFull, {**server_info})
        server_info_full["ip"] = None
        server_info_full["port"] = None

        return cls.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_name,
            sharing_name=sharing_name,
            sharing_ftype=sharing_ftype)

    @classmethod
    def server_info_satisfy_server_location_full(cls,
            server_info_full: ServerInfoFull, server_location: ServerLocation):
        """ Whether 'server_info_full' satisfy the given 'server_location' """

        return cls.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_location.name,
            server_ip=server_location.ip,
            server_port=server_location.port)

    @classmethod
    def server_info_satisfy_sharing_location_full(cls,
            server_info_full: ServerInfoFull, sharing_location: SharingLocation):
        """ Whether 'server_info_full' satisfy the given 'sharing_location' """

        return cls.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=FTYPE_DIR)

    @classmethod
    def server_info_satisfy_constraints_full(cls,
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

    @classmethod
    def _ask_overwrite(cls, fname: str, current_policy: OverwritePolicy) \
            -> Tuple[OverwritePolicy, OverwritePolicy]:  # cur_decision, new_default
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

            overwrite_answer = input(
                "{} already exists, overwrite it?\n"
                "y  : yes (default)\n"
                "n  : no\n"
                "N  : only if newer\n"
                "yy : yes - to all\n"
                "nn : no - to all\n"
                "NN : only if newer - to all\n".format(fname)
            )

            if not overwrite_answer or overwrite_answer == "y":
                cur_decision = OverwritePolicy.YES
            elif overwrite_answer == "n":
                cur_decision = OverwritePolicy.NO
            elif overwrite_answer == "N":
                cur_decision = OverwritePolicy.NEWER
            elif overwrite_answer == "yy":
                cur_decision = OverwritePolicy.YES
                new_default = OverwritePolicy.YES
            elif overwrite_answer == "nn":
                cur_decision = OverwritePolicy.NO
                new_default = OverwritePolicy.NO
            elif overwrite_answer == "NN":
                cur_decision = OverwritePolicy.NEWER
                new_default = OverwritePolicy.NEWER
            else:
                log.w("Invalid answer, asking again")

        return cur_decision, new_default

    @classmethod
    def _discover(
            cls,
            discover_port: int,
            discover_timeout: int,
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
                        print(ansi.DELETE_EOL, end="", flush=True)
                    elif state == DISCOVER_ABORTED:
                        # DISCOVER_ABORTED is always an error
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

        timedout = Discoverer(
            discover_addr=discover_addr,
            discover_port=discover_port,
            discover_timeout=discover_timeout,
            response_handler=response_handler).discover()

        # Restore the original handler
        signal.signal(signal.SIGINT, original_sigint_handler)

        # ------

        stop_pbar(DISCOVER_TIMEDOUT if timedout else DISCOVER_FOUND)

        if discover_ui_thread:
            # Wait for the ui
            discover_ui_thread.join()