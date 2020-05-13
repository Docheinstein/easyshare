import fcntl
import os
import select
import sys
import threading
import time
import zlib
from getpass import getpass
from stat import S_ISDIR, S_ISREG
from typing import Optional, Callable, List, Dict, Union, Tuple, TypeVar, cast

from Pyro5.errors import PyroError

from easyshare.common import transfer_port, DEFAULT_SERVER_PORT, DONE_COLOR, PROGRESS_COLOR
from easyshare.endpoint import Endpoint
from easyshare.es.commands import Commands, is_special_command, SPECIAL_COMMAND_MARK, Ls, Scan
from easyshare.es.common import ServerLocation, SharingLocation
from easyshare.es.connections import ServerConnection, SharingConnection, ServerConnectionMinimal
from easyshare.es.discover import Discoverer
from easyshare.es.errors import ClientErrors, print_error
from easyshare.es.ui import print_files_info_list, print_files_info_tree, \
    sharings_to_pretty_str, server_info_to_pretty_str
from easyshare.consts.net import ADDR_BROADCAST
from easyshare.esd.services import TransferService
from easyshare.logging import get_logger
from easyshare.protocol import FileInfo, FileInfoTreeNode
from easyshare.protocol import FTYPE_DIR, FTYPE_FILE, FileType
from easyshare.protocol import IRexecService, IGetService, IPutService
from easyshare.protocol import OverwritePolicy
from easyshare.protocol import Response, is_error_response, is_success_response, is_data_response
from easyshare.protocol import ServerInfoFull, ServerInfo
from easyshare.protocol import SharingInfo
from easyshare.progress import FileProgressor
from easyshare.styling import styled, red, bold
from easyshare.timer import Timer
from easyshare.ssl import get_ssl_context
from easyshare.sockets import SocketTcpOut
from easyshare.utils.app import eprint
from easyshare.utils.json import j
from easyshare.utils.pyro.client import TracedPyroProxy
from easyshare.utils.pyro.common import pyro_uri
from easyshare.utils.str import unprefix
from easyshare.utils.measures import duration_str_human, speed_str, size_str
from easyshare.utils.types import bytes_to_str, int_to_bytes, bytes_to_int
from easyshare.utils.os import ls, rm, tree, mv, cp, pathify, run_attached, relpath
from easyshare.args import Args as Args, Kwarg, INT_PARAM, PRESENCE_PARAM, ArgsParseError, Pargs, \
    VariadicPargs, ArgsParser, StopParseArgs

log = get_logger(__name__)


# ==================================================================



class TreeArgs(Pargs):
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]

    SHOW_ALL = ["-a", "--all"]
    SHOW_DETAILS = ["-l"]
    SHOW_SIZE = ["-S"]

    MAX_DEPTH = ["-d", "--depth"]

    def __init__(self, mandatory: int):
        super().__init__(mandatory, 1)

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (TreeArgs.SORT_BY_SIZE, PRESENCE_PARAM),
            (TreeArgs.REVERSE, PRESENCE_PARAM),
            (TreeArgs.GROUP, PRESENCE_PARAM),
            (TreeArgs.SHOW_ALL, PRESENCE_PARAM),
            (TreeArgs.SHOW_DETAILS, PRESENCE_PARAM),
            (TreeArgs.SHOW_SIZE, PRESENCE_PARAM),
            (TreeArgs.MAX_DEPTH, INT_PARAM),
        ]


class ScanArgs(Pargs):
    SHOW_DETAILS = ["-l"]

    def __init__(self):
        super().__init__(0, 0)

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (ScanArgs.SHOW_DETAILS, PRESENCE_PARAM),
        ]


class ListArgs(Pargs):
    SHOW_DETAILS = ["-l"]

    def __init__(self, mandatory: int):
        super().__init__(mandatory, 0)

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (ListArgs.SHOW_DETAILS, PRESENCE_PARAM),
        ]


class PingArgs(Pargs):
    COUNT = ["-c", "--count"]

    def __init__(self, mandatory: int):
        super().__init__(mandatory, 0)

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (PingArgs.COUNT, INT_PARAM),
        ]

class GetArgs(VariadicPargs):
    OVERWRITE_YES = ["-y", "--yes"]
    OVERWRITE_NO = ["-n", "--no"]
    OVERWRITE_NEWER = ["-N", "--newer"]
    CHECK = ["-c", "--check"]
    QUIET = ["-q", "--quiet"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (GetArgs.OVERWRITE_YES, PRESENCE_PARAM),
            (GetArgs.OVERWRITE_NO, PRESENCE_PARAM),
            (GetArgs.OVERWRITE_NEWER, PRESENCE_PARAM),
            (GetArgs.CHECK, PRESENCE_PARAM),
            (GetArgs.QUIET, PRESENCE_PARAM),
        ]

class PutArgs(VariadicPargs):
    OVERWRITE_YES = ["-y", "--yes"]
    OVERWRITE_NO = ["-n", "--no"]
    OVERWRITE_NEWER = ["-N", "--newer"]
    NEWER = ["-N", "--newer"]
    CHECK = ["-c", "--check"]
    QUIET = ["-q", "--quiet"]


    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (PutArgs.OVERWRITE_YES, PRESENCE_PARAM),
            (PutArgs.OVERWRITE_NO, PRESENCE_PARAM),
            (PutArgs.OVERWRITE_NEWER, PRESENCE_PARAM),
            (PutArgs.CHECK, PRESENCE_PARAM),
            (GetArgs.QUIET, PRESENCE_PARAM),
        ]


# ==================================================================


# ==================================================================

def _print(*vargs, **kwargs):
    print(*vargs, **kwargs)



def ensure_success_response(resp: Response):
    if is_error_response(resp):
        raise BadOutcome(resp.get("error"))
    if not is_success_response(resp):
        raise BadOutcome(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

def ensure_data_response(resp: Response, *data_fields):
    if is_error_response(resp):
        raise BadOutcome(resp.get("error"))
    if not is_data_response(resp):
        raise BadOutcome(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
    for data_field in data_fields:
        if data_field not in resp.get("data"):
            raise BadOutcome(ClientErrors.UNEXPECTED_SERVER_RESPONSE)


API = TypeVar('API', bound=Callable[..., None])



def provide_sharing_connection(api: API) -> API:
    def provide_sharing_connection_api_wrapper(client: 'Client', args: Args, _1: ServerConnection, _2: SharingConnection):
        # Wraps api providing the connection parameters.
        # The provided connection is the es current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if connection exists before invoking %s", api.__name__)

        sharing_conn, server_conn = \
            client._get_current_sharing_connection_or_create_from_sharing_location_args(args)

        if not sharing_conn or not server_conn or \
                not sharing_conn.is_connected() or not server_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        log.d("Connection established, invoking %s", api.__name__)
        api(client, args, server_conn, sharing_conn)

        if sharing_conn != client.sharing_connection:
            log.d("Closing temporary sharing connection")
            sharing_conn.close()

        if server_conn != client.server_connection:
            log.d("Closing temporary esd connection")
            server_conn.disconnect()

    provide_sharing_connection_api_wrapper.__name__ = api.__name__
    return provide_sharing_connection_api_wrapper

def make_server_connection_api_wrapper(api, connect: bool):
    def wrapper(client: 'Client', args: Args, _1: ServerConnection, _2: SharingConnection):
        # Wraps api providing the connection parameters.
        # The provided connection is the es current connection,
        # if it is established, or a temporary one that will be closed
        # just after the api call.
        # The connection is established treating the first arg of
        # args as a 'ServerLocation'
        log.d("Checking if esd connection exists before invoking %s", api.__name__)

        server_conn = client._get_current_server_connection_or_create_from_server_location_args(
            args,
            connect=connect
        )

        if not server_conn:
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        log.d("Server connection established, invoking %s", api.__name__)
        api(client, args, server_conn, None)

        if server_conn != client.server_connection:
            log.d("Disconnecting temporary esd connection")
            server_conn.disconnect()

    wrapper.__name__ = api.__name__

    return wrapper

def provide_server_connection_connected(api: API) -> API:
    return make_server_connection_api_wrapper(api, connect=True)

def provide_server_connection(api: API) -> API:
    return make_server_connection_api_wrapper(api, connect=False)

# ==================================================================

class BadOutcome(Exception):
    pass

# ==================================================================


class Client:

    def __init__(self, discover_port: int, discover_timeout: int):
        # self.connection: Optional[Connection] = None
        self.server_connection: Optional[ServerConnection] = None
        self.sharing_connection: Optional[SharingConnection] = None

        self._discover_port = discover_port
        self._discover_timeout = discover_timeout


        def LOCAL(parser: ArgsParser) -> ArgsParser:
            return parser

        def SERVER(connectionful_parser: ArgsParser, connectionless_parser: ArgsParser) -> ArgsParser:
            if self.is_connected_to_server():
                log.d("serverconnection_parser_provider -> 'already connect' parser")
                return connectionful_parser

            log.d("serverconnection_parser_provider -> 'not connect' parser")
            return connectionless_parser


        def SHARING(connectionful_parser: ArgsParser, connectionless_parser: ArgsParser) -> ArgsParser:
            if self.is_connected_to_sharing():
                log.d("sharingconnection_parser_provider -> 'already connect' parser")
                return connectionful_parser

            log.d("sharingconnection_parser_provider -> 'not connect' parser")
            return connectionless_parser


        # connectionful, connectionless, executor
        self._command_dispatcher: Dict[
            str, Tuple[
                Callable[..., ArgsParser],
                List[ArgsParser],
                Callable[[Args, Optional[ServerConnection], Optional[SharingConnection]], None]
            ]
        ] = {

            Commands.LOCAL_CHANGE_DIRECTORY: (
                LOCAL,
                [Pargs(0, 1)],
                Client.cd),
            Commands.LOCAL_LIST_DIRECTORY: (
                LOCAL,
                [Ls(0)],
                Client.ls),
            Commands.LOCAL_LIST_DIRECTORY_ENHANCED: (
                LOCAL,
                [Pargs(0, 1)],
                Client.l),
            Commands.LOCAL_TREE_DIRECTORY: (
                LOCAL,
                [TreeArgs(0)],
                Client.tree),
            Commands.LOCAL_CREATE_DIRECTORY: (
                LOCAL,
                [Pargs(1)],
                Client.mkdir),
            Commands.LOCAL_CURRENT_DIRECTORY: (
                LOCAL,
                [Pargs(0)],
                Client.pwd),
            Commands.LOCAL_REMOVE: (
                LOCAL,
                [VariadicPargs(1)],
                Client.rm),
            Commands.LOCAL_MOVE: (
                LOCAL,
                [VariadicPargs(2)],
                Client.mv),
            Commands.LOCAL_COPY: (
                LOCAL,
                [VariadicPargs(2)],
                Client.cp),
            Commands.LOCAL_EXEC: (
                LOCAL,
                [StopParseArgs(0)],
                Client.exec),

            Commands.REMOTE_CHANGE_DIRECTORY: (
                SHARING,
                [Pargs(0, 1), Pargs(1, 1)],
                self.rcd),
            Commands.REMOTE_LIST_DIRECTORY: (
                SHARING,
                [Ls(0), Ls(1)],
                self.rls),
            Commands.REMOTE_LIST_DIRECTORY_ENHANCED: (
                SHARING,
                [Pargs(0, 1), Pargs(1, 1)],
                self.rl),
            Commands.REMOTE_TREE_DIRECTORY: (
                SHARING,
                [TreeArgs(0), TreeArgs(1)],
                self.rtree),
            Commands.REMOTE_CREATE_DIRECTORY: (
                SHARING,
                [Pargs(1), Pargs(2)],
                self.rmkdir),
            Commands.REMOTE_CURRENT_DIRECTORY: (
                SHARING,
                [Pargs(0), Pargs(1)],
                self.rpwd),
            Commands.REMOTE_REMOVE: (
                SHARING,
                [VariadicPargs(1), VariadicPargs(2)],
                self.rrm),
            Commands.REMOTE_MOVE: (
                SHARING,
                [VariadicPargs(2), VariadicPargs(3)],
                self.rmv),
            Commands.REMOTE_COPY: (
                SHARING,
                [VariadicPargs(2), VariadicPargs(3)],
                self.rcp),
            Commands.REMOTE_EXEC: (
                SERVER,
                [StopParseArgs(0), StopParseArgs(1)],
                self.rexec),

            Commands.GET: (
                SHARING,
                [GetArgs(0), GetArgs(1)],
                self.get),

            Commands.PUT: (
                SHARING,
                [PutArgs(0), PutArgs(1)],
                self.put),


            Commands.SCAN: (
                LOCAL,
                [Scan()],
                self.scan),

            Commands.INFO: (
                SERVER,
                [Pargs(0, 1), Pargs(1, 0)],
                self.info),

            Commands.LIST: (
                SERVER,
                [ListArgs(0), ListArgs(1)],
                self.list),

            Commands.CONNECT: (
                SERVER,
                [Pargs(1), Pargs(1)],
                self.connect),
            Commands.DISCONNECT: (
                SERVER,
                [Pargs(0), Pargs(1)],
                self.disconnect),

            Commands.OPEN: (
                SERVER,
                [Pargs(1), Pargs(1)],
                self.open),
            Commands.CLOSE: (
                SHARING,
                [Pargs(0), Pargs(1)],
                self.close),

            Commands.PING: (
                SERVER,
                [PingArgs(0), PingArgs(1)],
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

    def execute_command(self, command: str, command_args: List[str]) -> Union[int, str]:
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

        except BadOutcome as ex:
            # "Expected" fail
            log.exception("BadOutcome: %s", str(ex.args[0]))
            return ex.args[0]

        except Exception as ex:
            # Every other unexpected fail: destroy connection
            log.exception("Exception caught while executing command\n%s", ex)
            self.destroy_connection()
            return ClientErrors.COMMAND_EXECUTION_FAILED

    def is_connected_to_server(self) -> bool:
        return True if self.server_connection and self.server_connection.is_connected() else False

    def is_connected_to_sharing(self) -> bool:
        return True if self.sharing_connection and self.sharing_connection.is_connected() else False
    # def is_connected(self) -> bool:
    #     return self.connection and self.connection.is_connected()

    # === LOCAL Commands ===

    @staticmethod
    def cd(args: Args, _, _2):
        directory = pathify(args.get_parg(default="~"))

        log.i(">> CD %s", directory)

        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            raise BadOutcome(ClientErrors.INVALID_PATH)

        os.chdir(directory)

    @staticmethod
    def ls(args: Args, _, _2):

        def ls_provider(path, **kwargs):
            path = pathify(path or os.getcwd())
            kws = {k: v for k, v in kwargs.items() if k in ["sort_by", "name", "reverse"]}
            return ls(path, **kws)

        Client._ls(args, data_provider=ls_provider, data_provider_name="LS")

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
            path = pathify(path or os.getcwd())
            kws = {k: v for k, v in kwargs.items() if k in ["sort_by", "name", "reverse", "max_depth"]}
            return tree(path, **kws)

        Client._tree(args, data_provider=tree_provider, data_provider_name="TREE")

    @staticmethod
    def mkdir(args: Args, _, _2):
        directory = pathify(args.get_parg())

        if not directory:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> MKDIR %s", directory)

        os.makedirs(directory, exist_ok=True)

    @staticmethod
    def pwd(_: Args, _2, _3):
        log.i(">> PWD")

        print(os.getcwd())

    @staticmethod
    def rm(args: Args, _, _2):
        paths = [pathify(p) for p in args.get_pargs()]

        if not paths:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RM %s", paths)

        for p in paths:
            rm(p, error_callback=lambda err: eprint(err))

    @staticmethod
    def mv(args: Args, _, _2):
        Client._mvcp(args, mv, "MV")

    @staticmethod
    def cp(args: Args, _, _2):
        Client._mvcp(args, cp, "CP")

    @staticmethod
    def exec(args: Args, _, _2):
        popen_cmd = args.get_pargs(default=[])
        popen_cmd_args = args.get_unparsed_args(default=[])
        popen_full_command = " ".join(popen_cmd + popen_cmd_args)

        log.i(">> EXEC %s", popen_full_command)

        retcode = run_attached(popen_full_command)
        if retcode != 0:
            log.w("Command failed with return code: %d", retcode)


    # =================================================
    # ================ SERVER Commands ================
    # =================================================


    def connect(self, args: Args, _1, _2):
        log.i(">> CONNECT")

        server_location = ServerLocation.parse(args.get_parg())

        # Just in case check whether we already connected to the right one
        if self.is_connected_to_server():
            if Client.server_info_satisfy_server_location(
                    self.server_connection.server_info,
                    server_location
            ):
                log.w("Current connection already satisfy esd location constraints")
                return

        # Actually create the connection
        new_server_conn = self._create_server_connection_from_server_location(
            ServerLocation.parse(args.get_parg()),
            connect=True
        )

        if not new_server_conn or not new_server_conn.is_connected():
            raise BadOutcome(ClientErrors.SERVER_NOT_FOUND)

        log.i("Server connection established")

        if self.is_connected_to_server():
            log.i("Disconnecting current esd connection before set the new one")
            self.server_connection.disconnect()

        self.server_connection = new_server_conn


    @provide_server_connection_connected
    def disconnect(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn or not server_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        log.i(">> DISCONNECT")

        server_conn.disconnect()

        # TODO: cleanup ?

    def open(self, args: Args, _1, _2):
        log.i(">> OPEN")

        new_server_conn: Optional[ServerConnection] = None
        new_sharing_conn: Optional[SharingConnection] = None

        # Check whether we are connected to a esd which owns the
        # sharing we are looking for, otherwise performs a scan
        sharing_location = SharingLocation.parse(args.get_parg())

        if not sharing_location:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        if self.is_connected_to_server():
            new_server_conn = self.server_connection

            if Client.server_info_satisfy_sharing_location(
                    self.server_connection.server_info,
                    sharing_location
            ):
                # The sharing is among the sharings of this connection
                log.d("The sharing we are looking for is among the sharings"
                      " of the already established esd connection")

                # Check whether we are already connected to it, just in case
                if self.is_connected_to_sharing() and \
                    self.sharing_connection.sharing_info.get("name") == sharing_location.name:
                    log.w("Current sharing connection already satisfy the sharing constraints")
                    return

                # Do an open() with this esd connection
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
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        # Close current stuff (if the new connections are actually new)

        if new_sharing_conn != self.sharing_connection and self.is_connected_to_sharing():
            log.d("Closing current sharing connection before set the new one")
            self.sharing_connection.close()

        if new_server_conn != self.server_connection and self.is_connected_to_server():
            log.i("Closing current esd connection before set the new one")
            self.server_connection.disconnect()


        log.i("Server and sharing connection established")
        self.sharing_connection = new_sharing_conn

        # Just mark that the esd connection has been created due open()
        # so that for symmetry close() will do disconnect() too
        if new_server_conn != self.server_connection:
            setattr(new_server_conn, "created_with_open", True)

        self.server_connection = new_server_conn


    @provide_server_connection_connected
    def rexec(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn or not server_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        popen_args = args.get_unparsed_args(default=[])
        popen_cmd = " ".join(popen_args)

        log.i(">> REXEC %s", popen_cmd)

        rexec_resp = server_conn.rexec(popen_cmd)
        ensure_data_response(rexec_resp)

        rexec_uid = rexec_resp.get("data")

        rexec_service_uri = pyro_uri(rexec_uid,
                                   self.server_connection.server_ip(),
                                   self.server_connection.server_port())

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

    @provide_server_connection
    def ping(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        count = args.get_kwarg_param(PingArgs.COUNT, default=None)

        i = 1
        while not count or i <= count:
            timer = Timer(start=True)
            resp = server_conn.ping()
            timer.stop()

            if is_data_response(resp) and resp.get("data") == "pong":
                print("[{}] OK      time={:.1f}ms".format(i, timer.elapsed_ms()))
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


            s += bold("{}. {} ({}:{})".format(
                    servers_found + 1,
                    server_info_full.get("name"),
                    server_info_full.get("ip"),
                    server_info_full.get("port"))) + "\n"

            if show_all_details:
                s += "\n" + server_info_to_pretty_str(server_info_full,
                                                      sharing_details=True) + "\n" + SEP
            else:
                s += sharings_to_pretty_str(server_info_full.get("sharings"),
                                            details=show_sharings_details,
                                            indent=2)

            print(s)

            servers_found += 1

            return True     # Continue DISCOVER

        Discoverer(
            discover_port=self._discover_port,
            discover_timeout=self._discover_timeout,
            response_handler=response_handler).discover()

        log.i("======================")

    @provide_server_connection
    def info(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        print(server_info_to_pretty_str(server_conn.server_info,
                                        separators=True))

    @provide_server_connection
    def list(self, args: Args, server_conn: ServerConnection, _):
        if not server_conn:
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        show_details = ScanArgs.SHOW_DETAILS in args

        log.i(">> LIST")

        resp = server_conn.list()
        ensure_data_response(resp)

        print(sharings_to_pretty_str(resp.get("data"),
                                     details=show_details))

    # =================================================
    # ================ SHARING Commands ===============
    # =================================================

    @provide_sharing_connection
    def close(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        log.i(">> CLOSE")

        sharing_conn.close()

        # noinspection PyUnresolvedReferences
        if server_conn and server_conn.is_connected() and \
                getattr(server_conn, "created_with_open", False):
            log.d("Closing esd connection too since opened due open")
            server_conn.disconnect()


    @provide_sharing_connection
    def rpwd(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        log.i(">> RPWD")
        resp = sharing_conn.rpwd()
        ensure_data_response(resp)

        rcwd = resp.get("data")
        print(rcwd)

    @provide_sharing_connection
    def rcd(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        directory = args.get_parg(default="/")

        log.i(">> RCD %s", directory)

        resp = sharing_conn.rcd(directory)
        ensure_data_response(resp)

        log.d("Current rcwd: %s", sharing_conn._rcwd)

    @provide_sharing_connection
    def rls(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        def rls_provider(f, **kwargs):
            resp = sharing_conn.rls(**kwargs, path=f)
            ensure_data_response(resp)
            return resp.get("data")

        Client._ls(args, data_provider=rls_provider, data_provider_name="RLS")

    def rl(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        # Just call rls -la
        # Reuse the parsed args for keep the (optional) path
        args._parsed[Ls.SHOW_ALL[0]] = True
        args._parsed[Ls.SHOW_DETAILS[0]] = True
        self.rls(args, server_conn, sharing_conn)

    @provide_sharing_connection
    def rtree(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        def rtree_provider(f, **kwargs):
            resp = sharing_conn.rtree(**kwargs, path=f)
            ensure_data_response(resp)
            return resp.get("data")

        Client._tree(args, data_provider=rtree_provider, data_provider_name="RTREE")

    @provide_sharing_connection
    def rmkdir(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        directory = args.get_parg()

        if not directory:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RMKDIR %s", directory)

        resp = sharing_conn.rmkdir(directory)
        ensure_success_response(resp)

    @provide_sharing_connection
    def rrm(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        paths = args.get_pargs()

        if not paths:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> RRM %s ", paths)

        resp = sharing_conn.rrm(paths)
        ensure_success_response(resp)

        if is_data_response(resp, "errors"):
            errors = resp.get("data").get("errors")
            log.e("%d errors occurred while doing rrm", len(errors))
            for err in errors:
                print_error(err)

    @provide_sharing_connection
    def rmv(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        Client._rmvcp(args, api=sharing_conn.rmv, api_name="RMV")

    @provide_sharing_connection
    def rcp(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        Client._rmvcp(args, api=sharing_conn.rcp, api_name="RCP")

    @provide_sharing_connection
    def get(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):
        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        files = args.get_pargs()

        do_check = PutArgs.CHECK in args
        quiet = PutArgs.QUIET in args

        resp = sharing_conn.get(files, check=do_check)
        ensure_data_response(resp, "uid")

        # Compute the remote daemon URI from the uid of the get() response
        get_service_uri = pyro_uri(resp.get("data").get("uid"),
                                   self.server_connection.server_ip(),
                                   self.server_connection.server_port())
        log.d("Remote GetService URI: %s", get_service_uri)

        # Raw transfer socket
        transfer_socket = SocketTcpOut(
            address=sharing_conn.server_info.get("ip"),
            port=transfer_port(sharing_conn.server_info.get("port")),
            ssl_context=get_ssl_context(),
        )

        # Overwrite preference

        if [GetArgs.OVERWRITE_YES in args, GetArgs.OVERWRITE_NO in args,
            GetArgs.OVERWRITE_NEWER].count(True) > 1:
            log.e("Only one between -n, -y and -N can be specified")
            raise BadOutcome("Only one between -n, -y and -N can be specified")

        overwrite_policy = OverwritePolicy.PROMPT

        if GetArgs.OVERWRITE_YES in args:
            overwrite_policy = OverwritePolicy.YES
        elif GetArgs.OVERWRITE_NO in args:
            overwrite_policy = OverwritePolicy.NO
        elif GetArgs.OVERWRITE_NEWER in args:
            overwrite_policy = OverwritePolicy.NEWER

        log.i("Overwrite policy: %s", str(overwrite_policy))

        # Stats

        progressor = None

        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Proxy

        get_service: Union[TracedPyroProxy, IGetService]

        with TracedPyroProxy(get_service_uri) as get_service:

            while True:
                log.i("Fetching another file info")
                # The first next() fetch never implies a new file to be put
                # on the transfer socket.
                # We have to check whether we want to eventually overwrite
                # the file, and then tell the esd next() if
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

                log.i("NEXT: %s of type %s", fname, ftype)

                # Case: DIR
                if ftype == FTYPE_DIR:
                    log.i("Creating dirs %s", fname)
                    os.makedirs(fname, exist_ok=True)
                    # if not quiet:
                    #     progressor.done()
                    continue  # No FTYPE_FILE => neither skip nor transfer for next()

                if ftype != FTYPE_FILE:
                    log.w("Cannot handle this ftype")
                    continue  # No FTYPE_FILE => neither skip nor transfer for next()

                # Case: FILE
                parent_dirs, _ = os.path.split(fname)
                if parent_dirs:
                    log.i("Creating parent dirs %s", parent_dirs)
                    os.makedirs(parent_dirs, exist_ok=True)

                # Check whether it already exists
                if os.path.isfile(fname):
                    log.w("File already exists, asking whether overwrite it (if needed)")

                    # Overwrite handling

                    timer.stop() # Don't take the user time into account
                    current_overwrite_decision, overwrite_policy = \
                        Client._ask_overwrite(fname, current_policy=overwrite_policy)
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
                            stat = os.lstat(fname)
                            do_skip = stat.st_mtime_ns >= fmtime
                            log.d("Local mtime: %d | Remote mtime: %d => skip: %s",
                                  stat.st_mtime_ns, fmtime, do_skip)

                        if do_skip:
                            log.d("Would have seek, have to tell esd to skip %s", fname)
                            get_next_resp = get_service.next(skip=True)
                            ensure_success_response(get_next_resp)
                            continue
                        else:
                            log.d("Not skipping")


                # Eventually tell the esd to begin the transfer
                # We have to call it now because the esd can't know
                # in advance if we want or not overwrite the file
                if will_seek:
                    log.d("Would have seek, have to tell esd to transfer %s", fname)
                    get_next_resp = get_service.next(transfer=True)
                    ensure_success_response(get_next_resp)
                # else: file already put into the transer socket

                if not quiet:
                    progressor = FileProgressor(
                        fsize,
                        description="GET " + fname,
                        color_progress=PROGRESS_COLOR,
                        color_done=DONE_COLOR
                    )

                log.i("Opening %s locally", fname)
                f = open(fname, "wb")

                cur_pos = 0
                expected_crc = 0

                while cur_pos < fsize:
                    recv_size = min(TransferService.BUFFER_SIZE, fsize - cur_pos)
                    log.i("Waiting chunk... (expected size: %dB)", recv_size)

                    chunk = transfer_socket.recv(recv_size)

                    if not chunk:
                        log.i("END")
                        raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)

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
                    written_size = os.path.getsize(fname)
                    if written_size != fsize:
                        log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                              fsize, written_size)
                        return # Really don't know how to recover from this disaster
                    else:
                        log.d("File length check: OK")

                n_files += 1
                if not quiet:
                    progressor.done()

            # Wait for completion
            outcome_resp = get_service.outcome()
            ensure_data_response(outcome_resp)
            outcome = outcome_resp.get("data")

            timer.stop()
            elapsed_s = timer.elapsed_s()

            transfer_socket.close()

            log.i("GET outcome: %d", outcome)

            if outcome > 0:
                log.e("GET reported an error: %d", outcome)
                raise BadOutcome(outcome)


            print("GET outcome: OK")
            print("Files        {}  ({})".format(n_files, size_str(tot_bytes)))
            print("Time         {}".format(duration_str_human(round(elapsed_s))))
            print("Avg. speed   {}".format(speed_str(tot_bytes / elapsed_s)))


    @provide_sharing_connection
    def put(self, args: Args, server_conn: ServerConnection, sharing_conn: SharingConnection):

        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        files = args.get_pargs()
        sendfiles: List[dict] = []

        if len(files) == 0:
            files = ["."]

        do_check = PutArgs.CHECK in args
        quiet = PutArgs.QUIET in args

        resp = sharing_conn.put(check=do_check)
        ensure_data_response(resp, "uid")

        # Compute the remote daemon URI from the uid of the get() response
        put_service_uri = pyro_uri(resp.get("data").get("uid"),
                                   self.server_connection.server_ip(),
                                   self.server_connection.server_port())
        log.d("Remote PutService URI: %s", put_service_uri)

        # Raw transfer socket
        transfer_socket = SocketTcpOut(
            address=sharing_conn.server_info.get("ip"),
            port=transfer_port(sharing_conn.server_info.get("port")),
            ssl_context=get_ssl_context(),
        )

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

            # if f == ".":
            #     # Special case
            #     dot_head, dot_trail = os.path.split(os.getcwd())
            #     _, dot_head_trail = os.path.split(dot_head)
            #     trail = os.path.join(dot_head_trail, dot_trail)
            # else:
            if f == ".":
                f = os.getcwd()

            f = f.replace("*", ".") # glob

            # standard case
            _, trail = os.path.split(f)

            log.i("-> trail: %s", trail)
            sendfile = {
                "local": f,
                "remote": trail
            }
            log.i("Adding sendfile %s", j(sendfile))
            sendfiles.append(sendfile)

        # Overwrite preference

        if [GetArgs.OVERWRITE_YES in args, GetArgs.OVERWRITE_NO in args,
            GetArgs.OVERWRITE_NEWER].count(True) > 1:
            log.e("Only one between -n, -y and -N can be specified")
            raise BadOutcome("Only one between -n, -y and -N can be specified")

        overwrite_policy = OverwritePolicy.PROMPT

        if PutArgs.OVERWRITE_YES in args:
            overwrite_policy = OverwritePolicy.YES
        elif PutArgs.OVERWRITE_NO in args:
            overwrite_policy = OverwritePolicy.NO
        elif PutArgs.OVERWRITE_NEWER in args:
            overwrite_policy = OverwritePolicy.NEWER

        log.i("Overwrite policy: %s", str(overwrite_policy))

        # Stats

        timer = Timer(start=True)
        tot_bytes = 0
        n_files = 0

        # Proxy

        put_service: Union[TracedPyroProxy, IPutService]

        with TracedPyroProxy(put_service_uri) as put_service:

            def send_file(local_path: str, remote_path: str):
                nonlocal overwrite_policy
                nonlocal tot_bytes
                nonlocal n_files

                progressor = None

                fstat = os.lstat(local_path)
                fsize = fstat.st_size

                if S_ISDIR(fstat.st_mode):
                    ftype = FTYPE_DIR
                elif S_ISREG(fstat.st_mode):
                    ftype = FTYPE_FILE
                else:
                    log.w("Unknown file type")
                    return

                finfo = {
                    "name": remote_path,
                    "ftype": ftype,
                    "size": fsize,
                    "mtime": fstat.st_mtime_ns
                }

                log.i("send_file finfo: %s", j(finfo))

                log.d("doing a put_next")

                put_next_resp = put_service.next(finfo,
                                                 overwrite_policy=overwrite_policy)
                ensure_data_response(put_next_resp)

                # Possible responses:
                # "accepted" => add the file to the transfer socket
                # "refused"  => do not add the file to the transfer socket
                # "ask_overwrite" => ask to the user and tell it to the esd
                #                    we got this response only if the overwrite
                #                    policy told to the esd is PROMPT

                # First of all handle the ask_overwrite, and contact the esd
                # again for tell the response
                if put_next_resp.get("data") == "ask_overwrite":
                    # Ask the user what to do

                    timer.stop() # Don't take the user time into account
                    current_overwrite_decision, overwrite_policy =\
                        Client._ask_overwrite(remote_path, current_policy=overwrite_policy)
                    timer.start()

                    if current_overwrite_decision == OverwritePolicy.NO:
                        log.i("Skipping " + remote_path)
                        return

                    # If overwrite policy is NEWER or YES we have to tell it
                    # to the esd so that it will take the right action
                    put_next_resp = put_service.next(finfo,
                                                     overwrite_policy=current_overwrite_decision)
                    ensure_success_response(put_next_resp)

                # The current put_next_resp is either the original one
                # or the one got after the ask_overwrite response we sent
                # to the esd.
                # By the way, it should not contain an ask_overwrite
                # since we specified a policy among YES/NEWER
                if put_next_resp.get("data") == "refused":
                    log.i("Skipping " + remote_path)
                    return

                if put_next_resp.get("data") != "accepted":
                    raise BadOutcome(ClientErrors.UNEXPECTED_SERVER_RESPONSE)

                local_path_pretty = os.path.normpath(local_path)
                if local_path.startswith(os.getcwd()):
                    local_path_pretty = relpath(unprefix(local_path_pretty, os.getcwd()))

                if not quiet:
                    progressor = FileProgressor(
                        fsize,
                        description="PUT " + local_path_pretty,
                        color_progress=PROGRESS_COLOR,
                        color_done=DONE_COLOR
                    )

                if ftype == FTYPE_DIR:
                    log.d("Sent a DIR, nothing else to do")
                    # if not quiet:
                    #     progressor.done()
                    return

                log.i("Opening %s locally", local_path)

                f = open(local_path, "rb")

                cur_pos = 0
                crc = 0

                while cur_pos < fsize:
                    # r = random.random() * 0.001
                    # time.sleep(0.001 + r)

                    chunk = f.read(TransferService.BUFFER_SIZE)
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

                f.close()

                n_files += 1
                if not quiet:
                    progressor.done()


            while sendfiles:
                log.i("Putting another file info")
                next_file = sendfiles.pop()

                # Check what is this
                # 1. Non existing: skip
                # 2. A file: send it directly (parent dirs won't be replicated)
                # 3. A dir: send it recursively

                next_file_local = next_file.get("local")
                next_file_remote = next_file.get("remote")

                if os.path.isfile(next_file_local):
                    # Send it directly
                    log.d("-> is a FILE")
                    send_file(next_file_local, next_file_remote)

                elif os.path.isdir(next_file_local):
                    # Send it recursively

                    log.d("-> is a DIR")

                    # Directory found
                    dir_files = sorted(os.listdir(next_file_local), reverse=True)

                    if dir_files:

                        log.i("Found a filled directory: adding all inner files to remaining_files")
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
                            log.i("Adding sendfile %s", j(sendfile))

                            sendfiles.append(sendfile)
                    else:
                        log.i("Found an empty directory")
                        log.d("Pushing an info for the empty directory")

                        send_file(next_file_local, next_file_remote)
                else:
                    eprint("Failed to send '{}'".format(next_file_local))
                    log.w("Unknown file type, doing nothing")

            log.i("Sending DONE")

            put_next_end_resp = put_service.next(None)
            ensure_success_response(put_next_end_resp)

            # Wait for completion
            outcome_resp = put_service.outcome()
            ensure_data_response(outcome_resp)
            outcome = outcome_resp.get("data")

            timer.stop()
            elapsed_s = timer.elapsed_s()

            transfer_socket.close()

            log.i("PUT outcome: %d", outcome)

            if outcome > 0:
                log.e("PUT reported an error: %d", outcome)
                raise BadOutcome(outcome)

            print("PUT outcome: OK")
            print("Files        {}  ({})".format(n_files, size_str(tot_bytes)))
            print("Time         {}".format(duration_str_human(round(elapsed_s))))
            print("Avg. speed   {}".format(speed_str(tot_bytes / elapsed_s)))


    @staticmethod
    def _ls(args: Args,
            data_provider: Callable[..., Optional[List[FileInfo]]],
            data_provider_name: str = "LS"):

        path = args.get_parg()
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

        ls_result = data_provider(path, sort_by=sort_by, reverse=reverse)

        if ls_result is None:
            raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)

        print_files_info_list(
            ls_result,
            show_file_type=Ls.SHOW_DETAILS in args,
            show_hidden=show_hidden,
            show_size=Ls.SHOW_SIZE in args or Ls.SHOW_DETAILS in args,
            compact=Ls.SHOW_DETAILS not in args
        )

    @staticmethod
    def _tree(args: Args,
              data_provider: Callable[..., Optional[FileInfoTreeNode]],
              data_provider_name: str = "TREE"):

        path = args.get_parg()
        reverse = TreeArgs.REVERSE in args
        show_hidden = TreeArgs.SHOW_ALL in args
        max_depth = args.get_kwarg_param(TreeArgs.MAX_DEPTH, default=None)

        sort_by = ["name"]

        if TreeArgs.SORT_BY_SIZE in args:
            sort_by.append("size")
        if TreeArgs.GROUP in args:
            sort_by.append("ftype")

        log.i(">> %s %s (sort by %s%s)",
              data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")

        tree_result: FileInfoTreeNode = data_provider(
            path,
            sort_by=sort_by, reverse=reverse,
            hidden=show_hidden, max_depth=max_depth
        )

        if tree_result is None:
            raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)

        print_files_info_tree(tree_result,
                              max_depth=max_depth,
                              show_hidden=show_hidden,
                              show_size=TreeArgs.SHOW_SIZE in args or TreeArgs.SHOW_DETAILS in args)

    @staticmethod
    def _mvcp(args: Args,
              primitive: Callable[[str, str], bool],
              primitive_name: str = "MV/CP"):
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
        mvcp_args = [pathify(f) for f in args.get_pargs()]

        if not mvcp_args or len(mvcp_args) < 2:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        dest = mvcp_args.pop()
        sources = mvcp_args

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest):
                log.e("'%s' must be an existing directory", dest)
                raise BadOutcome(ClientErrors.INVALID_PATH)

        # Every other constraint is well handled by shutil.move()
        errors = []

        for src in sources:
            log.i(">> %s '%s' '%s'", primitive_name, src, dest)
            try:
                primitive(src, dest)
            except Exception as ex:
                errors.append(str(ex))

        if errors:
            log.e("%d errors occurred", len(errors))

        for err in errors:
            eprint(err)

    @staticmethod
    def _rmvcp(args: Args,
               api: Callable[[List[str], str], Response],
               api_name: str = "RMV/RCP"):
        paths = args.get_pargs()

        if not paths:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        dest = paths.pop()

        if not dest or not paths:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        log.i(">> %s %s -> %s", api_name, str(paths), dest)

        resp = api(paths, dest)
        ensure_success_response(resp)

        if is_data_response(resp, "errors"):
            errors = resp.get("data").get("errors")
            log.e("%d errors occurred while doing %s", len(errors), api_name)
            for err in errors:
                print_error(err)


    def _get_current_sharing_connection_or_create_from_sharing_location_args(self, args: Args) \
            -> Tuple[SharingConnection, ServerConnection]:

        if self.is_connected_to_server() and self.is_connected_to_sharing():
            log.i("Providing already established sharing connection")
            return self.sharing_connection, self.server_connection

        # Create temporary connection
        log.i("No established sharing connection; creating a new one")

        pargs = args.get_pargs()

        if not pargs:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        sharing_location = SharingLocation.parse(pargs.pop(0))
        return self._create_sharing_connection_from_sharing_location(sharing_location)


    def _get_current_server_connection_or_create_from_server_location_args(
            self, args: Args, connect: bool) -> ServerConnection:

        if self.is_connected_to_server():
            log.i("Providing already established esd connection")
            return self.server_connection

        # Create temporary connection
        log.i("No established esd connection; creating a new one")

        pargs = args.get_pargs()

        if not pargs:
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)

        server_location = ServerLocation.parse(pargs.pop(0))
        return self._create_server_connection_from_server_location(
            server_location, connect=connect)


    def _create_sharing_connection_from_sharing_location(
            self, sharing_location: SharingLocation) -> Tuple[SharingConnection, ServerConnection]:
        server_conn = self._create_server_connection(
            connect=True,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=FTYPE_DIR,
        )

        if not server_conn or not server_conn.is_connected():
            raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)


        sharing_conn = Client.create_sharing_connection_from_server_connection(
            server_conn=server_conn,
            sharing_name=sharing_location.name,
        )

        if not sharing_conn or not sharing_conn.is_connected():
            raise BadOutcome(ClientErrors.SHARING_NOT_FOUND)

        return sharing_conn, server_conn


    def _create_server_connection_from_sharing_location(
            self, server_location: SharingLocation,
            connect: bool, sharing_ftype: FileType = None) -> ServerConnection:
        return self._create_server_connection(
            connect=connect,
            server_name=server_location.server_name,
            server_ip=server_location.server_ip,
            server_port=server_location.server_port,
            sharing_name=server_location.name,
            sharing_ftype=sharing_ftype

        )

    def _create_server_connection_from_server_location(
            self, server_location: ServerLocation, connect: bool) -> ServerConnection:
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

        server_port = server_port or DEFAULT_SERVER_PORT

        just_directly = False
        server_conn = None
        real_server_info = None

        if server_ip:
            server_ssl = False

            if server_port:
                log.d("Server IP and PORT are specified: trying to connect directly")
                just_directly = True # Everything specified => won't perform a scan
                # auto_server_info["port"] = server_port
            else:
                log.d("Server IP is specified: trying to connect directly to the default port")
                # auto_server_info["port"] = DEFAULT_SERVER_PORT

            while True: # actually two attempts are done: with/without SSL

                # Create a connection
                server_conn = ServerConnectionMinimal(
                    server_ip=server_ip,
                    server_port=server_port or DEFAULT_SERVER_PORT,
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
                    log.d("Connection established is UP, retrieved esd info\n%s",
                          j(real_server_info))

                    # Fill the uncomplete esd info with the IP/port we used to connect
                    break
                except Exception:
                    log.w("Connection cannot be established directly %s SSL",
                          "with" if server_ssl else "without")
                    # Invalidate connection
                    server_conn._destroy_connection()
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
                # Wraps the already established esd conn in a ServerConnection
                # associated with the right esd info


                if self.server_info_satisfy_constraints(
                        # DO not check esd identity: this is needed for allow servers
                        # behind NAT to be reached without know the real internal IP/port
                        real_server_info,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND directly")
                    server_conn = ServerConnection(
                        server_ip=server_ip,
                        server_port=server_port,
                        server_info=real_server_info,
                        established_server_connection=server_conn.server
                    )
            elif server_conn:
                # Invalidate connection
                server_conn._destroy_connection()
                server_conn = None

        # Eventually performs the scan
        if not server_conn:
            if just_directly:
                log.d("Connection not established directly and DISCOVER won't be "
                      "performed since IP and PORT has been specified both")
            else:
                log.d("Will perform a DISCOVER for establish esd connection")
                real_server_info = self._discover_server(
                    server_name=server_name, server_ip=server_ip, server_port=server_port,
                    sharing_name=sharing_name, sharing_ftype=sharing_ftype
                )

                if self.server_info_satisfy_constraints_full(
                        real_server_info,
                        server_name=server_name, server_ip=server_ip, server_port=server_port,
                        sharing_name=sharing_name, sharing_ftype=sharing_ftype):

                    log.d("Server info satisfy the constraints: FOUND w/ discover")
                    server_conn = ServerConnection(
                        server_ip=real_server_info.get("ip"),
                        server_port=real_server_info.get("port"),
                        server_info=real_server_info
                    )

        if not server_conn:
            log.e("Connection can't be established")
            raise BadOutcome(ClientErrors.CONNECTION_ERROR)

        # We have a valid TCP connection with the esd
        log.i("Connection established with %s:%d",
              server_conn.server_ip(),
              server_conn.server_port())

        # We have a valid TCP connection with the esd
        log.d("-> same as %s:%d",
              server_conn.server_info.get("ip"),
              server_conn.server_info.get("port"))

        # Check whether we have to do connect()
        # (It might be unnecessary for public esd api such as ping, info, list, ...)
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

    @staticmethod
    def create_sharing_connection_from_server_connection(
            server_conn: ServerConnection, sharing_name: str) -> SharingConnection:
        if not server_conn:
            raise BadOutcome(ClientErrors.NOT_CONNECTED)

        # Create the sharing connection: open()

        open_resp = server_conn.open(sharing_name)
        ensure_data_response(open_resp)

        sharing_uid = open_resp.get("data")

        # Take out the sharing info from the esd info
        for shinfo in server_conn.server_info.get("sharings"):
            if shinfo.get("name") == sharing_name:
                log.d("Found the sharing info among server_info sharings")

                sharing_conn = SharingConnection(
                    sharing_uid,
                    sharing_info=shinfo,
                    server_info=server_conn.server_info
                )

                return sharing_conn

        raise BadOutcome(ClientErrors.SHARING_NOT_FOUND)

    def _discover_sharing(
            self, sharing_location: SharingLocation, ftype: FileType = None) -> \
            Tuple[Optional[SharingInfo], Optional[ServerInfoFull]]:
        pass
        # call _discover and takes the info from its sharings

    def _discover_server(
            self,
            server_name: str = None, server_ip: str = None,
            server_port: int = None, sharing_name: str = None,
            sharing_ftype: FileType = None) -> ServerInfoFull:

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

        Discoverer(
            discover_port=self._discover_port,
            discover_addr=server_ip or ADDR_BROADCAST,
            discover_timeout=self._discover_timeout,
            response_handler=response_handler).discover()

        return server_info


    @staticmethod
    def server_info_satisfy_server_location(
            server_info: ServerInfo, server_location: ServerLocation):
        return Client.server_info_satisfy_constraints(
                server_info,
                server_name=server_location.name)

    @staticmethod
    def server_info_satisfy_sharing_location(
            server_info: ServerInfo, sharing_location: SharingLocation):
        return Client.server_info_satisfy_constraints(
                server_info,
                server_name=sharing_location.server_name,
                sharing_name=sharing_location.name,
                sharing_ftype=FTYPE_DIR)

    @staticmethod
    def server_info_satisfy_constraints(
            server_info: ServerInfo,
            server_name: str = None,
            sharing_name: str = None, sharing_ftype: FileType = None) -> bool:
        # Make a shallow copy
        server_info_full: ServerInfoFull = cast(ServerInfoFull, {**server_info})
        server_info_full["ip"] = None
        server_info_full["port"] = None

        return Client.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_name,
            sharing_name=sharing_name,
            sharing_ftype=sharing_ftype)

    @staticmethod
    def server_info_satisfy_server_location_full(
            server_info_full: ServerInfoFull, server_location: ServerLocation):
        return Client.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=server_location.name,
            server_ip=server_location.ip,
            server_port=server_location.port)

    @staticmethod
    def server_info_satisfy_sharing_location_full(
            server_info_full: ServerInfoFull, sharing_location: SharingLocation):
        return Client.server_info_satisfy_constraints_full(
            server_info_full,
            server_name=sharing_location.server_name,
            server_ip=sharing_location.server_ip,
            server_port=sharing_location.server_port,
            sharing_name=sharing_location.name,
            sharing_ftype=FTYPE_DIR)

    @staticmethod
    def server_info_satisfy_constraints_full(
            server_info: ServerInfoFull,
            server_name: str = None, server_ip: str = None, server_port: int = None,
            sharing_name: str = None, sharing_ftype: FileType = None) -> bool:

        if not server_info:
            return False

        # Server name
        if server_name and server_name != server_info.get("name"):
            log.d("Server info does not match the esd name filter '%s'",
                  server_name)
            return False

        # Server IP
        if server_ip and server_ip != server_info.get("ip"):
            log.d("Server info does not match the esd ip filter '%s'",
                  server_ip)
            return False

        # Server  port
        if server_port and server_port != server_info.get("port"):
            log.d("Server info does not match the esd port filter '%s'",
                  server_ip)
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
                    continue

                # FOUND
                log.i("Server info satisfies constraints")
                break
            else:
                log.w("Server info constraints satisfied but the specified "
                      "sharing can't be found")
                return False # Not found

        return True

    @staticmethod
    def _ask_overwrite(fname: str, current_policy: OverwritePolicy) \
            -> Tuple[OverwritePolicy, OverwritePolicy]:  # cur_decision, new_default

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

    def destroy_connection(self):
        try:
            log.d("Destroying connection and invalidating it")
            if self.is_connected_to_server():
                self.server_connection.disconnect()
        except:
            log.w("Clean disconnection failed, invalidating connection anyway")
        finally:
            self.server_connection = None
            self.sharing_connection = None