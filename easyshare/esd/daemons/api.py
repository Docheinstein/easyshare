import mmap
import os
import threading
import zlib
from collections import OrderedDict, deque
from pathlib import Path
from typing import List, Dict, Callable, Optional, Union, Tuple, BinaryIO, Deque

from easyshare.auth import Auth
from easyshare.common import TransferDirection, TransferProtocol, BEST_BUFFER_SIZE, APP_VERSION, \
    DEFAULT_TRANSFER_SOCKET_TIMEOUT
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, ClientContext
from easyshare.esd.daemons import TcpDaemon
from easyshare.logging import get_logger
from easyshare.protocol.requests import Request, is_request, Requests, RequestParams, RequestsParams
from easyshare.protocol.responses import create_error_response, ServerErrors, Response, create_success_response, \
    create_error_of_response, ResponsesParams
from easyshare.protocol.types import ServerInfo, FTYPE_DIR, RexecEventType, create_file_info, FTYPE_FILE, \
    create_file_info_full, FileInfo, ftype_of
from easyshare.sockets import SocketTcp, SocketTcpIn
from easyshare.ssl import get_ssl_context
from easyshare.streams import StreamClosedError
from easyshare.styling import green, red
from easyshare.tracing import trace_json
from easyshare.utils.env import is_unix
from easyshare.utils.json import btoj, jtob, j
from easyshare.utils.os import ls, os_error_str, tree, cp, mv, rm, user, pty_detached, \
    find, du, set_mtime, is_newer
from easyshare.utils.path import is_hidden
from easyshare.utils.str import q
from easyshare.utils.types import is_str, is_list, is_bool, is_valid_list, itob, btoi

if is_unix():
    from ptyprocess import PtyProcess


log = get_logger(__name__)


# SPath and FPath are Path with a different semantic:
SPath = Path # sharing path, is relative and bounded to the sharing domain
FPath = Path # file system path, absolute, starts from the server's file system root

class ApiDaemon(TcpDaemon):

    def __init__(self, address, port,
                 *,
                 sharings: List[Sharing],
                 name: str,
                 auth: Auth,
                 rexec: bool):
        super().__init__(address, port)

        self._sharings = {s.name: s for s in sharings}
        self._name = name
        self._auth = auth
        self._rexec_enabled = rexec

        self._clients_lock = threading.Lock()
        self._clients: Dict[Endpoint, ClientHandler] = {}

    def sharings(self) -> Dict[str, Sharing]:
        return self._sharings

    def name(self) -> str:
        return self._name

    def auth(self) -> Auth:
        """ Authentication """
        return self._auth

    def is_rexec_enabled(self) -> bool:
        """ Whether rexec is enabled """
        return self._rexec_enabled


    def server_info(self) -> ServerInfo:
        """ Returns a 'ServerInfo' of this server service"""
        si = {
            "name": self._name,
            "sharings": [sh.info() for sh in self._sharings.values()],
            "ssl": True if get_ssl_context() is not None else False,
            "auth": True if (self._auth and self._auth.algo_security() > 0) else False,
            "rexec": self._rexec_enabled,
            "version": APP_VERSION
        }

        return si

    def _handle_connection(self, sock: SocketTcpIn):
        log.i(f"Received new client connection from {sock.remote_endpoint()}")
        self._add_client(sock)


    def _add_client(self, client_sock: SocketTcp):
        client = ClientContext(client_sock)
        client_handler = ClientHandler(client, self)
        log.i(f"Adding client {client}")
        # no need to lock, still in single thread execution
        self._clients[client.endpoint] = client_handler

        th = threading.Thread(target=client_handler.handle)
        th.start()


# decorator
def require_server_connection(api):
    def require_server_connection_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not handler._connected_to_server:
            return handler._create_error_response(ServerErrors.NOT_CONNECTED)
        return api(handler, params)
    return require_server_connection_wrapper

# decorator
def require_sharing_connection(api):
    def require_sharing_connection_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not handler._connected_to_sharing:
            return handler._create_error_response(ServerErrors.NOT_CONNECTED)
        return api(handler, params)
    return require_sharing_connection_wrapper


# decorator
def require_unix(api):
    def require_unix_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not is_unix():
            return handler._create_error_response(ServerErrors.SUPPORTED_ONLY_FOR_UNIX)
        return api(handler, params)
    return require_unix_wrapper


# decorator
def require_rexec_enabled(api):
    def require_rexec_enabled_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not handler._api_daemon.is_rexec_enabled():
            return handler._create_error_response(ServerErrors.REXEC_DISABLED)
        return api(handler, params)
    return require_rexec_enabled_wrapper


# decorator
def require_d_sharing(api):
    """
    Decorator that aborts the requests if the sharing is not a "directory sharing"
    """
    def require_d_sharing_wrapper(handler: 'ClientHandler', params: RequestParams):
        if handler._current_sharing.ftype != FTYPE_DIR:
            log.e(f"Forbidden: command allowed only for DIR sharing by [{handler._client}]")
            return handler._create_error_response(ServerErrors.NOT_ALLOWED_FOR_F_SHARING)
        return api(handler, params)

    return require_d_sharing_wrapper

# decorator
def require_write_permission(api):
    """
    Decorator that aborts the request if a write operation
    is performed on a readonly sharing.
    """
    def require_write_permission_wraper(handler: 'ClientHandler', params: RequestParams):
        if handler._current_sharing.read_only:
            log.e(f"Forbidden: write action on read only sharing by [{handler._client}]")
            return handler._create_error_response(ServerErrors.NOT_WRITABLE)
        return api(handler, params)

    return require_write_permission_wraper

class ClientHandler:

    def __init__(self, client: ClientContext, api_daemon: ApiDaemon):
        self._api_daemon = api_daemon

        self._client = client

        self._connected_to_server: Optional[bool] = None
            # initial limbo state
            # True is after connect() - False is after disconnect()
        self._connected_to_sharing: bool = False
        self._current_sharing: Optional[Sharing] = None
        self._current_rcwd_fpath: Optional[FPath] = None

        self._request_dispatcher: Dict[str, Callable[[RequestParams], Response]] = {
            Requests.CONNECT: self._connect,
            Requests.DISCONNECT: self._disconnect,
            Requests.LIST: self._list,
            Requests.INFO: self._info,
            Requests.PING: self._ping,
            Requests.OPEN: self._open,
            Requests.CLOSE: self._close,
            # Requests.REXEC: self._rexec,
            Requests.RSHELL: self._rshell,
            Requests.RCD: self._rcd,
            Requests.RPWD: self._rpwd,
            Requests.RSTAT: self._rstat,
            Requests.RLS: self._rls,
            Requests.RTREE: self._rtree,
            Requests.RFIND: self._rfind,
            Requests.RDU: self._rdu,
            Requests.RMKDIR: self._rmkdir,
            Requests.RRM: self._rrm,
            Requests.RMV: self._rmv,
            Requests.RCP: self._rcp,
            Requests.GET: self._get,
            Requests.PUT: self._put,
        }


    @property
    def _current_rcwd_spath(self) -> SPath:
        return self._spath_rel_to_root_of_fpath(self._current_rcwd_fpath)


    def handle(self):
        log.i(f"Handling client {self._client}")

        print(green(f"[{self._client.tag}] connected "
                    f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))

        while self._client.stream.is_open() and \
                self._connected_to_server is not False:
                    # check _connected_to_server against False,
                    # since None is the limbo state which is allowed (before connect)
            try:
                req = self._recv_json()
                if is_request(req):
                    try:
                        resp_payload = self._handle_request(req)
                    except:
                        log.eexception("Exception occurred while handling request")
                        resp_payload = self._create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

                else:
                    log.e("Invalid request - discarding it")
                    resp_payload = self._create_error_response(ServerErrors.INVALID_REQUEST)

                self._send_response(resp_payload)
            except StreamClosedError:
                pass # self._client.stream.is_open() will fail next iter
            except:
                log.eexception("Unexpected exception occurred")
                # Maybe we could recover from this point, but
                # break is probably safer for avoid zombie connections
                break

        if self._client.stream.is_open():   # the socket could be still open
                                            # if disconnect() has been called
            try:
                log.d("Trying to close underlying socket")
                self._client.stream.close()
            except:
                log.w("Underlying socket not closed gracefully")

        log.i(f"Connection closed with client {self._client}")

        print(red(f"[{self._client.tag}] disconnected "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))


    def _recv_json(self, timeout: float=None) -> Dict:
        # don't trace at byte level
        req_payload_data = self._client.stream.read(timeout=timeout, trace=False)
        req_payload = None

        try:
            req_payload = btoj(req_payload_data)
        except:
            log.eexception("Failed to parse payload - discarding it")

        # Trace IN
        trace_json(
            req_payload,
            sender=self._client.socket.remote_endpoint(), receiver=self._client.socket.endpoint(),
            direction=TransferDirection.IN, protocol=TransferProtocol.TCP
        )

        return req_payload

    def _handle_request(self, request: Request) -> Response:
        api = request.get("api")
        if not api:
            return self._create_error_response(ServerErrors.INVALID_REQUEST)

        if api not in self._request_dispatcher:
            return self._create_error_response(ServerErrors.UNKNOWN_API)

        return self._request_dispatcher[api](request.get("params", {}))

    def _send_response(self, response: Response):
        if not response:
            log.d("null response, sending nothing")
            return

        # Trace OUT
        trace_json(
            response,
            sender=self._client.socket.endpoint(), receiver=self._client.socket.remote_endpoint(),
            direction=TransferDirection.OUT, protocol=TransferProtocol.TCP
        )

        # Really send it back
        # don't trace at byte level
        self._client.stream.write(jtob(response), trace=False)


    # == SERVER COMMANDS ==

    def _connect(self, params: RequestParams) -> Response:
        log.i(f"<< CONNECT  |  {self._client}")

        password = params.get("password")

        if self._connected_to_server:
            log.w("Client already connected")
            return create_success_response()

        # Authentication
        log.i(f"Authentication check - type: {self._api_daemon.auth().algo_type()}")

        # Just ask the auth whether it matches or not
        # (The password can either be none/plain/hash, the auth handles them all)
        if not self._api_daemon.auth().authenticate(password):
            log.e("Authentication FAILED")
            return self._create_error_response(ServerErrors.AUTHENTICATION_FAILED)
        else:
            log.i("Authentication OK")

        self._connected_to_server = True

        print(f"[{self._client.tag}] connect {'*' * len(password) if password else ''} "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response()

    @require_server_connection
    def _disconnect(self, _: RequestParams):
        log.i(f"<< DISCONNECT  |  {self._client}")

        if not self._connected_to_server:
            log.w("Already disconnected")

        self._connected_to_server = False

        print((f"[{self._client.tag}] disconnect "
               f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))

        return create_success_response()

    def _list(self, _: RequestParams):
        log.i(f"<< LIST  |  {self._client}")

        print(f"[{self._client.tag}] list "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(
            [sh.info() for sh in self._api_daemon.sharings().values()])

    def _info(self, _: RequestParams):
        log.i(f"<< INFO  |  {self._client}")

        print(f"[{self._client.tag}] info "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(self._api_daemon.server_info())

    def _ping(self, _: RequestParams):
        log.i(f"<< PING  |  {self._client}")

        print(f"[{self._client.tag}] ping "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response("pong")

    @require_server_connection
    @require_unix
    @require_rexec_enabled
    def _rshell(self, params: RequestParams):

        cmd = params.get(RequestsParams.RSHELL_CMD)
        cols = params.get(RequestsParams.RSHELL_COLS)
        rows = params.get(RequestsParams.RSHELL_ROWS)

        if not cmd:
            cmd = user().pw_shell

        log.i(f"<< RSHELL {cmd}  |  {self._client}")

        if not cols or not rows:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        # OK - report it
        print(f"[{self._client.tag}] rshell '{cmd}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        def out_hook(data: bytes):
            log.d(f"{data}")
            self._client.stream.write(
                RexecEventType.DATA_B + data, trace=True
            )

        def end_hook(retcode: int):
            log.d(f"END {retcode}")
            self._client.stream.write(
                RexecEventType.RETCODE_B + itob(retcode % 255, length=1),
                trace=True
            )

        def stdin_receiver(ptyprocess: PtyProcess):
            while True:
                in_b = self._client.stream.read(trace=True)
                event_type: int = in_b[0]
                log.d(f"Event type = {event_type}")

                if event_type == RexecEventType.DATA:
                    data = in_b[1:]
                    log.d(f"< {data}")
                    ptyprocess.write(data)
                elif event_type == RexecEventType.EOF:
                    log.d("< EOF")
                    ptyprocess.close()
                elif event_type == RexecEventType.KILL:
                    log.d("< KILL")
                    ptyprocess.terminate()
                elif event_type == RexecEventType.ENDACK:
                    log.d("< ENDACK")
                    break
                else:
                    log.w(f"Can't handle event of type {event_type}")

        try:
            ptyproc = pty_detached(
                out_hook=out_hook,
                end_hook=end_hook,
                cols=cols,
                rows=rows,
                cmd=cmd
            )

            self._send_response(create_success_response())

            # Receive stdin from client
            stdin_th = threading.Thread(target=stdin_receiver, args=(ptyproc,))
            stdin_th.start()

            # Wait everybody
            stdin_th.join()
            ptyproc.wait()
            log.d("RSHELL finished")

        except Exception as ex:
            log.eexception(f"Rshell failed: {ex}")
            return self._create_error_response(ServerErrors.REXEC_EXECUTION_FAILED)

    @require_server_connection
    def _open(self, params: RequestParams):
        sharing_name = params.get(RequestsParams.OPEN_SHARING)

        log.i(f"<< OPEN {sharing_name}  |  {self._client}")

        if not sharing_name:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        sharing: Sharing = self._api_daemon.sharings().get(sharing_name)

        if not sharing:
            return self._create_error_response(ServerErrors.SHARING_NOT_FOUND, q(sharing_name))

        print(f"[{self._client.tag}] open '{sharing.name}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        self._connected_to_sharing = True
        self._current_sharing = sharing
        self._current_rcwd_fpath = sharing.path

        return create_success_response(sharing.info())

    # == SHARING COMMANDS ==

    @require_sharing_connection
    def _close(self, _: RequestParams):
        log.i(f"<< CLOSE  |  {self._client}")

        print(f"[{self._client.tag}] close "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        self._connected_to_sharing = False
        self._current_sharing = None
        self._current_rcwd_fpath = None

        return create_success_response()


    @require_sharing_connection
    @require_d_sharing
    def _rcd(self, params: RequestParams) -> Response:
        spath = params.get(RequestsParams.RCD_PATH) or "/"

        log.i(f"<< RCD {spath}  |  {self._client}")

        if not is_str(spath):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        new_rcwd_fpath = self._fpath_joining_rcwd_and_spath(spath)

        log.d(f"Would cd into: {new_rcwd_fpath}")

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(new_rcwd_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(spath))

        # Check if it actually exists
        if not new_rcwd_fpath.is_dir():
            return self._create_error_response(ServerErrors.NOT_A_DIRECTORY, new_rcwd_fpath)

        # The path is allowed and exists, setting it as new rcwd
        self._current_rcwd_fpath = new_rcwd_fpath

        log.i(f"New valid rcwd: {self._current_rcwd_fpath}")

        # Tell the client the new rcwd
        rcwd_spath_str = str(self._current_rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        log.d(f"RCWD for the client: {rcwd_spath_str}")

        print(f"[{self._client.tag}] rcd '{self._current_rcwd_fpath}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(rcwd_spath_str)

    @require_sharing_connection
    @require_d_sharing
    def _rpwd(self, _: RequestParams) -> Response:
        log.i(f"<< RPWD  |  {self._client}")

        rcwd_spath_str = str(self._current_rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        print(f"[{self._client.tag}] rpwd "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(rcwd_spath_str)

    @require_sharing_connection
    def _rstat(self, params: RequestParams):
        paths = params.get(RequestsParams.GET_PATHS)

        log.i(f"<< RSTAT  {paths}  |  {self._client}")

        if not paths:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        errors = []
        infos = {}
        for p in paths:
            fpath = self._fpath_joining_rcwd_and_spath(p)

            if self._is_fpath_allowed(fpath):
                try:
                    infos[p] = create_file_info_full(fpath, raise_exceptions=True)
                    # OK - report it
                    print(f"[{self._client.tag}] rstat '{fpath}' "
                          f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
                except:
                    log.e(f"Failed to stat over {fpath}")
                    errors.append(create_error_of_response(ServerErrors.INVALID_PATH, q(p)))
            else:
                log.e("Path is invalid (out of sharing domain)")
                errors.append(create_error_of_response(ServerErrors.INVALID_PATH, q(p)))

        if errors:
            return create_error_response(errors)

        return create_success_response(infos)

    @require_sharing_connection
    def _rls(self, params: RequestParams):
        path = params.get(RequestsParams.RLS_PATH) or "."
        sort_by = params.get(RequestsParams.RLS_SORT_BY) or ["name"]
        reverse = params.get(RequestsParams.RLS_REVERSE) or False
        hidden = params.get(RequestsParams.RLS_HIDDEN) or False
        details = params.get(RequestsParams.RLS_DETAILS) or False

        log.i(f"<< RLS {path}  |  {self._client}")

        if not is_str(path) or not is_list(sort_by, str) or not is_bool(reverse) \
            or not is_bool(hidden) or not is_bool(details):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        ls_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d(f"Would ls into: {ls_fpath}")

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(ls_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i(f"Going to ls on valid path {ls_fpath}")

        try:
            ls_result = ls(ls_fpath,
                           sort_by=sort_by, reverse=reverse,
                           hidden=hidden, details=details)

            # OK - report it
            print(f"[{self._client.tag}] rls '{ls_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except Exception as exc:
            log.eexception("rls exception occurred")

            if isinstance(exc, FileNotFoundError):
                return self._create_error_response(ServerErrors.NOT_EXISTS, ls_fpath)
            if isinstance(exc, PermissionError):
                return self._create_error_response(ServerErrors.PERMISSION_DENIED, ls_fpath)
            if isinstance(exc, OSError):
                return self._create_error_response(ServerErrors.GENERAL_ERROR, os_error_str(exc), ls_fpath)

            return self._create_error_response(ServerErrors.GENERAL_ERROR, exc, ls_fpath)

        log.i(f"RLS response {ls_result}")

        return create_success_response(ls_result)

    @require_sharing_connection
    @require_d_sharing
    def _rtree(self, params: RequestParams):
        path = params.get(RequestsParams.RTREE_PATH) or "."
        sort_by = params.get(RequestsParams.RTREE_SORT_BY) or ["name"]
        reverse = params.get(RequestsParams.RTREE_REVERSE) or False
        hidden = params.get(RequestsParams.RTREE_HIDDEN) or False
        max_depth = params.get(RequestsParams.RTREE_DEPTH)
        details = params.get(RequestsParams.RTREE_DETAILS) or False

        log.i(f"<< RTREE {path} |  {self._client}")

        if not is_str(path) or not is_list(sort_by, str) or not is_bool(reverse) \
            or not is_bool(details):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        tree_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d(f"Would tree into: {tree_fpath}")

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(tree_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i(f"Going to tree on valid path {tree_fpath}")

        try:
            tree_root = tree(tree_fpath,
                             sort_by=sort_by, reverse=reverse,
                             hidden=hidden, max_depth=max_depth,
                             details=details)

            # OK - report it
            print(f"[{self._client.tag}] rtree '{tree_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except Exception as exc:
            log.eexception("rtree exception occurred")

            if isinstance(exc, FileNotFoundError):
                return self._create_error_response(ServerErrors.NOT_EXISTS, tree_fpath)
            if isinstance(exc, PermissionError):
                return self._create_error_response(ServerErrors.PERMISSION_DENIED, tree_fpath)
            if isinstance(exc, OSError):
                return self._create_error_response(ServerErrors.GENERAL_ERROR, os_error_str(exc), tree_fpath)

            return self._create_error_response(ServerErrors.GENERAL_ERROR, exc, tree_fpath)

        log.i(f"RTREE response {j(tree_root)}")

        return create_success_response(tree_root)


    @require_sharing_connection
    def _rfind(self, params: RequestParams):
        path = params.get(RequestsParams.RFIND_PATH) or "."
        name = params.get(RequestsParams.RFIND_NAME)
        regex = params.get(RequestsParams.RFIND_REGEX)
        case_sensitive = params.get(RequestsParams.RFIND_CASE_SENSITIVE)
        ftype = params.get(RequestsParams.RFIND_FTYPE)
        details = params.get(RequestsParams.RFIND_DETAILS) or False
        max_depth = params.get(RequestsParams.RFIND_MAX_DEPTH)

        log.i(f"<< RFIND {path}  |  {self._client}")

        if case_sensitive is None:
            case_sensitive = True

        if not is_str(path) or \
                (name and not is_str(name)) or \
                (regex and not is_str(regex)) or \
                (not is_bool(case_sensitive)) or \
                ftype not in [None, FTYPE_DIR, FTYPE_FILE]:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        find_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d(f"Would find into: {find_fpath}")

        # Check if it's inside the sharing domainF
        if not self._is_fpath_allowed(find_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i(f"Going to find on valid path {find_fpath}")

        try:
            find_result = find(find_fpath,
                               name=name,
                               regex=regex,
                               case_sensitive=case_sensitive,
                               ftype=ftype,
                               details=details,
                               max_depth=max_depth,
                               file_info_name_provider=lambda p: str(self._spath_rel_to_rcwd_of_fpath(p)))

            # OK - report it
            print(f"[{self._client.tag}] rfind '{find_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except Exception as exc:
            log.eexception("rfind exception occurred")

            if isinstance(exc, FileNotFoundError):
                return self._create_error_response(ServerErrors.NOT_EXISTS, find_fpath)
            if isinstance(exc, PermissionError):
                return self._create_error_response(ServerErrors.PERMISSION_DENIED, find_fpath)
            if isinstance(exc, OSError):
                return self._create_error_response(ServerErrors.GENERAL_ERROR, os_error_str(exc), find_fpath)

            return self._create_error_response(ServerErrors.GENERAL_ERROR, exc, find_fpath)

        log.i(f"RFIND response {find_result}")

        return create_success_response(find_result)


    @require_sharing_connection
    def _rdu(self, params: RequestParams):
        path = params.get(RequestsParams.RDU_PATH) or "."

        log.i(f"<< RDU {path}  |  {self._client}")

        if not is_str(path):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        rdu_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d(f"Would rdu into: {rdu_fpath}")

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(rdu_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i(f"Going to du on valid path {rdu_fpath}")

        try:
            # OK - report it
            print(f"[{self._client.tag}] rdu '{rdu_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

            usage = du(rdu_fpath)

        except Exception as exc:
            log.eexception("rdu exception occurred")

            if isinstance(exc, FileNotFoundError):
                return self._create_error_response(ServerErrors.NOT_EXISTS, rdu_fpath)
            if isinstance(exc, PermissionError):
                return self._create_error_response(ServerErrors.PERMISSION_DENIED, rdu_fpath)
            if isinstance(exc, OSError):
                return self._create_error_response(ServerErrors.GENERAL_ERROR, os_error_str(exc), rdu_fpath)

            return self._create_error_response(ServerErrors.GENERAL_ERROR, exc, rdu_fpath)

        log.i(f"RDU response {usage}")

        return create_success_response([
            [str(self._spath_rel_to_root_of_fpath(rdu_fpath)), usage]
        ])

    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rmkdir(self, params: RequestParams):
        directory = params.get(RequestsParams.RMKDIR_PATH)

        log.i(f"<< RMKDIR {directory}  |  {self._client}")

        if not is_str(directory):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        directory_fpath = self._fpath_joining_rcwd_and_spath(directory)
        log.d(f"Would create directory: {directory_fpath}")

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(directory_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(directory))

        log.i(f"Going to mkdir on valid path {directory_fpath}")

        try:
            directory_fpath.mkdir(parents=True)
            # OK - report it
            print(f"[{self._client.tag}] rmkdir '{directory_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except Exception as exc:
            log.eexception("rdu exception occurred")

            if isinstance(exc, FileNotFoundError):
                return self._create_error_response(ServerErrors.NOT_EXISTS, directory_fpath)
            if isinstance(exc, PermissionError):
                return self._create_error_response(ServerErrors.PERMISSION_DENIED, directory_fpath)
            if isinstance(exc, OSError):
                return self._create_error_response(ServerErrors.GENERAL_ERROR, os_error_str(exc), directory_fpath)

            return self._create_error_response(ServerErrors.GENERAL_ERROR, exc, directory_fpath)

        return create_success_response()

    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rrm(self, params: RequestParams):
        paths = params.get(RequestsParams.RRM_PATHS)

        log.i(f"<< RRM {paths}  |  {self._client}")

        if not is_valid_list(paths, str):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        errors = []

        for p in paths:
            fpath = self._fpath_joining_rcwd_and_spath(p)

            if self._is_fpath_allowed(fpath):
                errcnt = len(errors)
                err = self._rm(fpath)

                if err:
                    errors.append(err)

                new_errcnt = len(errors)
                # OK - report it (even if failures might happen within it)
                #    - at least notify the number of failures, if any
                failures_str = f"- {new_errcnt - errcnt} failures " if new_errcnt > errcnt else ""
                report = (f"[{self._client.tag}] rrm '{fpath}' {failures_str}"
                          f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
                print(report)
            else:
                log.e("Path is invalid (out of sharing domain)")
                errors.append(create_error_of_response(ServerErrors.INVALID_PATH, q(p)))

        if errors:
            return create_error_response(errors)

        return create_success_response()

    def _rm(self, path: Path) -> Optional[str]:

        log.i(f"RM '{path}'")

        error = None

        def handle_rm_error(exc: Exception, p: Path):
            nonlocal error

            log.eexception("rm exception occurred")

            if isinstance(exc, PermissionError):
                error = create_error_of_response(ServerErrors.RRM_PERMISSION_DENIED,
                                                 *self._qspathify(p))
            elif isinstance(exc, FileNotFoundError):
                error = create_error_of_response(ServerErrors.RRM_NOT_EXISTS,
                                                 *self._qspathify(p))
            elif isinstance(exc, OSError):
                error = create_error_of_response(ServerErrors.RRM_OTHER_ERROR,
                                                 os_error_str(exc),
                                                 *self._qspathify(p))
            else:
                error = create_error_of_response(ServerErrors.RRM_OTHER_ERROR,
                                                 exc,
                                                 *self._qspathify(p))

        rm(path, error_callback=handle_rm_error)

        return error


    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rcp(self, params: RequestParams):
        sources = params.get(RequestsParams.RCP_SOURCES)
        dest = params.get(RequestsParams.RCP_DESTINATION)

        errors = []

        def handle_errno(errno: int, *subjects):
            errors.append(create_error_of_response(errno, *subjects))

        def handle_cp_exception(exc: Exception, src: FPath, dst: FPath):
            log.eexception("rcp exception occurred")

            if isinstance(exc, PermissionError):
                errors.append(create_error_of_response(ServerErrors.RCP_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(create_error_of_response(ServerErrors.RCP_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                errors.append(create_error_of_response(ServerErrors.RCP_OTHER_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                errors.append(create_error_of_response(ServerErrors.RCP_OTHER_ERROR,
                                                       exc, *self._qspathify(src, dst)))

        resp = self._rmvcp(sources, dest, cp, "rcp",
                           errno_callback=handle_errno,
                           exception_callback=handle_cp_exception)
        if resp:
            return resp  # e.g. invalid path

        if errors:
            return create_error_response(errors)  # e.g. permission denied

        return create_success_response()


    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rmv(self, params: RequestParams):
        sources = params.get(RequestsParams.RMV_SOURCES)
        dest = params.get(RequestsParams.RMV_DESTINATION)

        errors = []

        def handle_errno(errno: int, *subjects):
            errors.append(create_error_of_response(errno, *subjects))

        def handle_mv_exception(exc: Exception, src: FPath, dst: FPath):
            log.eexception("rmv exception occurred")

            if isinstance(exc, PermissionError):
                errors.append(create_error_of_response(ServerErrors.RMV_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(create_error_of_response(ServerErrors.RMV_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                errors.append(create_error_of_response(ServerErrors.RMV_OTHER_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                errors.append(create_error_of_response(ServerErrors.RMV_OTHER_ERROR,
                                                       exc, *self._qspathify(src, dst)))

        resp = self._rmvcp(sources, dest, mv, "rmv",
                           errno_callback=handle_errno,
                           exception_callback=handle_mv_exception)

        if resp:
            return resp  # e.g. invalid path

        if errors:
            return create_error_response(errors)  # e.g. permission denied

        return create_success_response()



    def _rmvcp(self,
               sources: List[str], destination: str,
               primitive: Callable[[Path, Path], bool],
               primitive_name: str = "mv/cp",
               errno_callback: Callable[..., None] = None,
               exception_callback: Callable[[Exception, FPath, FPath], None] = None) -> Optional[Response]:

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

        if not is_valid_list(sources, str) or not is_str(destination):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        destination_fpath = self._fpath_joining_rcwd_and_spath(destination)

        if not self._is_fpath_allowed(destination_fpath):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_error_response(ServerErrors.INVALID_PATH, q(destination))

        # sources_paths will be checked after, since if we are copy more than
        # a file and only one is invalid we won't throw a global exception

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not destination_fpath.is_dir():
                log.e(f"'{destination_fpath}' must be an existing directory")
                return self._create_error_response(ServerErrors.NOT_A_DIRECTORY, destination_fpath)


        log.i(f"<< {primitive_name.upper()}  |  {self._client}")

        for source_path in sources:
            source_fpath = self._fpath_joining_rcwd_and_spath(source_path)

            # Path validity check
            if self._is_fpath_allowed(source_fpath):
                try:
                    log.i(f"{primitive_name} {source_fpath} -> {destination_fpath}")
                    primitive(source_fpath, destination_fpath)
                    # OK - report it
                    print(f"[{self._client.tag}] {primitive_name} '{source_fpath}' '{destination_fpath}' "
                          f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
                except Exception as ex:
                    if exception_callback:
                        exception_callback(ex, source_fpath, destination_fpath)
            else:
                log.e("Path is invalid (out of sharing domain)")

                if errno_callback:
                    errno_callback(ServerErrors.INVALID_PATH, q(source_path))

        return None



    @require_sharing_connection
    # @require_d_sharing
    def _get(self, params: RequestParams):
        paths = params.get(RequestsParams.GET_PATHS)
        check = params.get(RequestsParams.GET_CHECK)
        no_hidden = params.get(RequestsParams.GET_NO_HIDDEN, False)

        if not paths:
            paths = ["."]

        # Secret params
        chunk_size = params.get(RequestsParams.GET_CHUNK_SIZE, BEST_BUFFER_SIZE)
        use_mmap = params.get(RequestsParams.GET_MMAP, True)

        log.i(f"<< GET {paths}  |  {self._client}")

        self._send_response(create_success_response())

        transfer_socket = self._client.socket

        # Next file/directory to serve
        next_servings: Deque[Tuple[FPath, FPath, str]] = deque([]) # fpath, basedir, prefix

        errors = []
        aborted = False

        # 1. For each path of paths calculate the real version of the path
        # based on our file system, eventually discarding illegal paths (e.g. ../something)
        # We calculate the tuple (fpath, basedir, prefix) where
        # - fpath: the path based on our file system
        # - basedir: the path based on our file system from which the download
        #            occurs for the client (e.g. if == fpath the downled file is not
        #            wrapped, if == fpath.parent is wrapped in folder called as
        #            ther parent
        # - prefix: eventual prefix to prepend to the name of the download for
        #           the client (is useful if basedir can't be safely used because
        #           will be outside sharing domain, i.e. when the root of the sharing
        #           is about to be downloaded)

        for f in paths:
            # "." is equal to "" and means get the rcwd wrapped into a folder
            p = Path(f)
            log.d(f"f = {f}")
            log.d(f"p(f) = {p}")

            # Compute the absolute path depending on the user request (p)
            # and our current rcwd
            fpath = self._fpath_joining_rcwd_and_spath(p)

            is_root = fpath == self._current_sharing.path
            log.d(f"is root = {is_root}")

            # Compute the basedir: the directory from which the user takes
            # the files (this will have effect on the location of the files on
            # the client)
            # If the last component is a *, consider the entire content of the folder (unwrapped)
            # Otherwise the basedir is the parent (so that the folder will be wrapped)

            prefix = ""

            if is_root: # don't go outside "."
                basedir = fpath
                prefix = self._current_sharing.name
            else:
                basedir = fpath.parent

            log.d(f"fpath(f) = {fpath}")
            log.d(f"basedir(f) = {basedir}")
            log.d(f"prefix = {self._current_sharing.name}")

            # Do domain check now, after this check it should not be
            # necessary to check it since we can only go deeper

            if self._is_fpath_allowed(fpath) and self._is_fpath_allowed(basedir):
                next_servings.appendleft((fpath, basedir, prefix))
            else:
                log.e(f"Path {f} is invalid (out of sharing domain)")
                errors.append(create_error_of_response(ServerErrors.INVALID_PATH,
                                                       q(f)))

        # --------------

        # 2. Cyclically wait for "next" requests and send the respective file

        def get_next() -> Union[Tuple[FPath, BinaryIO], None]: # fpath, fd
            next_transfer = None

            while not next_transfer:
                # len(next_servings) is checked within the loop
                # after the request

                log.d("Waiting for next() request from client...")

                # 1. Receive the request from the client

                # e.g. {skip: False, transfer: True} // client doesn't provide the path
                req = self._recv_json(timeout=DEFAULT_TRANSFER_SOCKET_TIMEOUT)

                if not req:
                    self._send_response(self._create_error_response(ServerErrors.INVALID_REQUEST))
                    continue

                if len(next_servings) == 0:
                    log.i("No more files: transfer completed. Sending END")
                    self._send_response(create_success_response())
                    break

                next_transfer = handle_get_next_request(req)

                if next_transfer is False:
                    break

            # Either next_transfer is valid or we have finished
            return next_transfer

        def handle_get_next_request(req: Dict) -> Union[Tuple[FPath, BinaryIO], None, bool]: # fpath, fd
            nonlocal aborted

            while True:
                action = req.get(RequestsParams.GET_NEXT_ACTION)
                if action not in RequestsParams.GET_NEXT_ACTIONS:
                    log.w(f"Unknown action: {action}")
                    action = RequestsParams.GET_NEXT_ACTION_SEEK

                log.i(f"<< GET_NEXT action = {action}")

                if action == RequestsParams.GET_NEXT_ACTION_ABORT:
                    log.w("Client has request an abort")
                    aborted = True
                    return False

                # 2. Serve the file
                # -> send response to the client anyway
                # -> return only if there is a file to transfer

                # Get next file (or dir)
                # Do not pop it now: either transfer os skip must be specified
                # for a regular file before being popped out
                # (In this way we can handle cases in which the client don't
                # want to receive the file (because of overwrite, or anything else)
                next_fpath, next_basedir, next_prefix = next_servings[len(next_servings) - 1]

                log.d(f"Next file fpath: {next_fpath}")
                log.d(f"Next file basedir: {next_basedir}")

                # Check domain validity
                # Should never fail since we have already checked in __init__
                if not self._is_fpath_allowed(next_fpath) or \
                        not self._is_fpath_allowed(next_basedir):
                    log.e("Path is invalid (out of sharing domain)")
                    next_servings.pop()
                    # can't even provide a name for the error since
                    # we only have fpath at this point
                    errors.append(create_error_of_response(ServerErrors.INVALID_PATH,
                                                           q(f)))
                    continue

                log.d("Sharing domain check OK")

                # Compute the path relative to the basedir (depends on the user request)
                # e.g. can be public/f1 or ../public or /path/to/dir ...
                next_spath_str = os.path.join(next_prefix, next_fpath.relative_to(next_basedir))

                log.d(f"Next file spath: {next_spath_str}")

                # Check if it's hidden

                if no_hidden and is_hidden(next_fpath):
                    log.d(f"Not sending {next_fpath} since no_hidden is True")
                    next_servings.pop()
                    continue

                finfo = create_file_info(
                    next_fpath,
                    name=next_spath_str
                )

                # Case: FILE
                if finfo and next_fpath.is_file():
                    next_transfer = None

                    log.i(f"NEXT FILE: {next_fpath}")

                    # Pop only if transfer or skip is specified
                    if action == RequestsParams.GET_NEXT_ACTION_TRANSFER or \
                            action == RequestsParams.GET_NEXT_ACTION_SKIP:
                        log.d("Popping file out (transfer OR skip specified for FTYPE_FILE)")
                        next_servings.pop()
                        if action == RequestsParams.GET_NEXT_ACTION_TRANSFER:
                            # Actually put the file on the queue of the files
                            # to be send through the transfer socket

                            # Before doing so, try to open the file for real.
                            # At least we are able to detect any error (e.g. perm denied)
                            # before say the client that the transfer is began
                            # We have to report the error now (create_error_response)
                            # not later (_add_error()) because the user have to
                            # take a decision based on this (skip the file)
                            log.d("Trying to open file before initializing transfer")

                            try:
                                fd = next_fpath.open("rb")
                                log.d(f"Able to open file: {next_fpath}")

                                log.d("Actually adding file to the transfer queue")
                                next_transfer = (next_fpath, fd)
                            except FileNotFoundError:
                                log.w("Can't open file - not transferring file (file not found error)")
                                self._send_response(
                                    create_error_response(ServerErrors.NOT_EXISTS,
                                                          q(next_spath_str))
                                )
                                return None
                            except PermissionError:
                                log.w("Can't open file - not transferring file (permission error)")
                                self._send_response(
                                    create_error_response(ServerErrors.PERMISSION_DENIED,
                                                          q(next_spath_str))
                                )
                                return None
                            except OSError as oserr:
                                log.w("Can't open file - not transferring file (oserror)")
                                self._send_response(
                                    create_error_response(ServerErrors.GENERAL_ERROR,
                                                          os_error_str(oserr),
                                                          q(next_spath_str))
                                )
                                return None
                            except Exception as exc:
                                log.w("Can't open file - not transferring file")
                                self._send_response(
                                    create_error_response(ServerErrors.GENERAL_ERROR,
                                                          exc,
                                                          q(next_spath_str))
                                )
                                return None

                    self._send_response(
                        create_success_response({
                            ResponsesParams.GET_NEXT_FILE: finfo
                        })
                    )

                    return next_transfer # might be null if action is not "transfer"

                # Case: DIR
                elif finfo and next_fpath.is_dir():
                    log.i(f"NEXT DIR: {next_fpath}")

                    # Pop it now; it doesn't make sense ask the user whether
                    # skip or overwrite as for files
                    next_servings.pop()

                    # Directory found
                    try:
                        dir_files: List[FPath] = sorted(list(next_fpath.iterdir()), reverse=False)
                    except FileNotFoundError:
                        errors.append(create_error_of_response(ServerErrors.NOT_EXISTS,
                                                               q(next_spath_str)))
                        continue
                    except PermissionError:
                        errors.append(create_error_of_response(ServerErrors.PERMISSION_DENIED,
                                                               q(next_spath_str)))
                        continue
                    except OSError as oserr:
                        errors.append(create_error_of_response(ServerErrors.GENERAL_ERROR,
                                                                 os_error_str(oserr),
                                                                 q(next_spath_str)))
                        continue
                    except Exception as exc:
                        errors.append(create_error_of_response(ServerErrors.GENERAL_ERROR,
                                                                 exc,
                                                                 q(next_spath_str)))
                        continue

                    if dir_files:
                        log.i("Found a filled directory: adding all inner files to remaining_files")
                        for file_in_dir in dir_files:
                            log.i(f"Adding {file_in_dir}")
                            next_servings.appendleft((file_in_dir, next_basedir, prefix))
                    else:
                        log.i("Found an empty directory")
                        log.d("Sending an info for the empty directory")

                        self._send_response(
                            create_success_response({
                                ResponsesParams.GET_NEXT_FILE: finfo
                            })
                        )
                        return None
                # Case: UNKNOWN (non-existing/link/special files/...)
                else:
                    # Pop it now
                    next_servings.pop()
                    log.w(f"Not file nor dir? skipping {next_fpath}")
                    errors.append(create_error_of_response(ServerErrors.GET_TRANSFER_SKIPPED,
                                                           q(next_spath_str)))
                    continue


        while True:
            log.d("Blocking and waiting for a file to handle...")

            next_transf = get_next()

            if not next_transf:
                log.i("No more files: transfer completed")
                break

            next_transf_fpath: FPath
            next_transf_f: BinaryIO

            next_transf_fpath, next_transf_f = next_transf

            log.i(f"Next outgoing file to handle: {next_transf_fpath}")

            # OK - report it
            print(f"[{self._client.tag}] get '{next_transf_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

            file_len = next_transf_fpath.stat().st_size

            # File is already opened
            source = next_transf_f

            if use_mmap:
                try:
                    # try to mmap the file to memory
                    source = mmap.mmap(next_transf_f.fileno(), 0,
                                       prot=mmap.PROT_READ)
                except Exception as ex:
                    log.w(f"mmap failed, will read directly from file for reason: {ex}")

            # TODO:
            #  if something about IO goes wrong all the transfer is compromised
            #  since we can't tell the user about it.
            #  BTW open is already done so there should be no permissions problems.

            cur_pos = 0
            crc = 0

            # Send file


            while cur_pos < file_len:
                readlen = min(file_len - cur_pos, chunk_size)

                # Read from the file/mmap
                chunk = source.read(readlen)

                if not chunk:
                    # EOF
                    log.i(f"Finished to handle: {next_transf_fpath}")
                    break

                log.h(f"Read chunk of {len(chunk)}B")
                cur_pos += len(chunk)


                if check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                log.h(f"{cur_pos}/{file_len} ({cur_pos / file_len * 100:.2f})")

                transfer_socket.send(chunk)


            log.i(f"Closing file {next_transf_fpath}")
            next_transf_f.close()
            if source != next_transf_f:
                source.close() # mmap

            # Eventually send the CRC in-band
            if check:
                log.d(f"Sending CRC: {crc}")
                transfer_socket.send(itob(crc, 4))

        log.i("GET finished")

        resp_data = {
            ResponsesParams.GET_OUTCOME: not aborted
        }

        if errors:
            resp_data[ResponsesParams.GET_ERRORS] = errors

        return create_success_response(resp_data)



    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _put(self, params: RequestParams):
        check = params.get(RequestsParams.PUT_CHECK)
        preview = params.get(RequestsParams.PUT_PREVIEW)
        dest = params.get(RequestsParams.PUT_DEST)
        is_multiple = params.get(RequestsParams.PUT_IS_MULTIPLE)

        # Hidden

        log.i(f"<< PUT {'(preview)' if preview else ''}  |  {self._client}")

        self._send_response(create_success_response())

        transfer_socket = self._client.socket

        errors = []
        outcome = True

        sync_table: Optional[Dict[str, None]] = None
        sync_table_entries = []

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
                # i.e.
                # <rcwd>/<spath>            if spath is relative
                # <sharing_path>/<spath>    if spath is absolute ( /... )
                return self._fpath_joining_rcwd_and_spath(fname_)

            source_ftype = "any"
            if not is_multiple:
                source_ftype = FTYPE_DIR if len(Path(fname_).parts) > 1 else finfo_.get("ftype")

            dest_ftype = ftype_of(self._fpath_joining_rcwd_and_spath(dest))

            log.d(f"Handling destpath for case "
                  f"{(2 if is_multiple else 1)}_{source_ftype or 'any'}2{dest_ftype or 'none'}")

            if not is_multiple:
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
                        raise ValueError("Invalid --dest semantic")
                elif source_ftype == FTYPE_DIR:
                    if not dest_ftype:
                        # 1_dir2none -> replace dir name
                        output = dest / Path(*(fname_.parts[1:]))
                    elif dest_ftype == FTYPE_FILE:
                        # 1_dir2file -> ERROR
                        raise ValueError("Invalid --dest semantic: destination must be a directory")
                    elif dest_ftype == FTYPE_DIR:
                        # 1_dir2dir
                        output = dest / fname_
                    else: # WTF
                        raise ValueError("Invalid --dest semantic")
                else:
                    raise ValueError("Invalid --dest semantic")
            else:
                if dest_ftype == FTYPE_FILE:
                    # 2_any2file (ok)
                    raise ValueError("Invalid --dest semantic: destination must be a directory")
                elif dest_ftype == FTYPE_DIR:
                    # 2_any2dir (ok)
                    output = dest / fname_
                else:
                    # 2_any2none (ok)
                    raise ValueError("Invalid --dest semantic: destination must exists")

            return self._fpath_joining_rcwd_and_spath(output)

        def add_to_sync_table(fpath: FPath):
            nonlocal sync_table_entries

            log.d(f"Adding sync entries for path: '{fpath}'")

            findings = find(fpath)
            sync_table_entries += [f.get("name") for f in findings]

            log.d(f"# sync table entries = {len(sync_table_entries)}")
            log.d(f"{j(sync_table_entries)}")

        def compute_sync_table():
            nonlocal sync_table

            # Preserve order for perform RM in optimal order (parents first)
            sync_table = OrderedDict({entry: None for entry in sync_table_entries})
            log.d(f"SYNC table computed ({len(sync_table_entries)})\n" +
                  "\n".join(sync_table.keys()))

        def put_next():
            nonlocal outcome

            while True:
                log.d("Waiting for next() request from client...")

                # 1. Receive the request from the client

                # e.g. {file: {name: f1, size: 293}, overwrite: "..."} // client doesn't provide the path

                req = self._recv_json(timeout=DEFAULT_TRANSFER_SOCKET_TIMEOUT)

                # File info
                finfo = req.get(RequestsParams.PUT_NEXT_FILE)
                do_sync = req.get(RequestsParams.PUT_NEXT_SYNC)

                if not finfo:
                    log.i("<< PUT_NEXT DONE")
                    self._send_response(create_success_response())
                    break

                fname = finfo.get("name")
                ftype = finfo.get("ftype")
                fsize = finfo.get("size")
                fmtime = finfo.get("mtime")

                if fname is None or ftype is None or fsize is None or fmtime is None:
                    self._send_response(self._create_error_response(
                        ServerErrors.INVALID_REQUEST)
                    )
                    continue

                # Overwrite
                overwrite = req.get(RequestsParams.PUT_NEXT_OVERWRITE)
                if overwrite not in RequestsParams.PUT_NEXT_OVERWRITES:
                    log.w("Unspecified overwrite, using PROMPT")
                    overwrite = RequestsParams.PUT_NEXT_OVERWRITE_PROMPT

                log.i(f"<< PUT_NEXT {j(finfo)}")

                # Compute local path, taking dest into account
                try:
                    fpath = compute_dest_path(finfo)
                except Exception as exc:
                    outcome = False
                    log.e(f"Invalid dest semantic {exc}")
                    err_resp = self._create_error_response(
                        ServerErrors.PUT_INVALID_DEST_SEMANTIC, q(fname))
                    err_resp[ResponsesParams.PUT_ABORT] = True

                    self._send_response(err_resp)
                    # the abort flag is only a suggestion, we will continue
                    # the put_next loop (the expected behaviour is that the client
                    # will send us an empty file (i.e. a DONE) the next iteration
                    continue

                log.d(f"fpath = {fpath}")

                if not self._is_fpath_allowed(fpath):
                    log.e(f"Path '{fpath}' is invalid (out of sharing domain)")
                    self._send_response(self._create_error_response(
                        ServerErrors.INVALID_PATH, q(fname))
                    )
                    continue

                log.d("Sharing domain check OK")

                # If sync is True track the files in the directory
                # so that we can remove old files (the one for which no file info
                # is retrieved from the server) after the transfer completes.
                if do_sync:
                    if sync_table is None:  # check is None because if the dir is new
                                            # sync table could be already initialized but empty
                        add_to_sync_table(fpath)

                    # Remove from the SYNC table eventually
                    # Do the removal for each possible path within local_path
                    # (so that we won't delete parent folder if the change is
                    # inside the children)

                if sync_table_entries:
                    incremental_path = Path.cwd()
                    for part in fpath.parts:
                        incremental_path = incremental_path / part
                        incremental_path_str = str(incremental_path)
                        log.d(f"Removing from SYNC table: '{incremental_path_str}'")
                        try:
                            sync_table_entries.remove(incremental_path_str)
                            log.d(f"Actually removed, len is now = {len(sync_table_entries)}")
                        except:
                            pass

                already_exists = fpath.exists()

                # Check whether is a dir or a file
                if ftype == FTYPE_DIR:
                    # Handle dir now by creating dirs
                    if not preview:
                        log.i(f"Creating dirs {fpath}")
                        fpath.mkdir(parents=True, exist_ok=True)
                    self._send_response(create_success_response({
                        ResponsesParams.PUT_NEXT_STATUS:
                            ResponsesParams.PUT_NEXT_STATUS_ACCEPTED,
                        ResponsesParams.PUT_NEXT_ALREADY_EXISTS: already_exists
                    }))
                    continue

                if not ftype == FTYPE_FILE:  # wtf
                    self._send_response(self._create_error_response(
                        ServerErrors.INVALID_COMMAND_SYNTAX)
                    )
                    continue

                if ftype == FTYPE_FILE:
                    fpath_parent = fpath.parent
                    if fpath_parent:
                        if not preview:
                            log.i(f"Creating parent dirs {fpath_parent}")
                            fpath_parent.mkdir(parents=True, exist_ok=True)

                # Check whether it already exists
                if fpath.is_file():
                    def skip_transfer():
                        self._send_response(create_success_response({
                            ResponsesParams.PUT_NEXT_STATUS:
                                ResponsesParams.PUT_NEXT_STATUS_REFUSED,
                            ResponsesParams.PUT_NEXT_ALREADY_EXISTS: already_exists
                        }))

                    log.w(f"File already exists; deciding what to do based on overwrite policy: {overwrite}")

                    # Take a decision based on the overwrite policy
                    if overwrite == RequestsParams.PUT_NEXT_OVERWRITE_PROMPT:
                        log.d("Overwrite policy is PROMPT, asking the client whether overwrite")
                        self._send_response(create_success_response({
                            ResponsesParams.PUT_NEXT_STATUS:
                                ResponsesParams.PUT_NEXT_STATUS_UNCERTAIN,
                            ResponsesParams.PUT_NEXT_FILE_INFO:
                                create_file_info(fpath, name=str(self._spath_rel_to_root_of_fpath(fpath))),
                            ResponsesParams.PUT_NEXT_ALREADY_EXISTS: already_exists
                        }))
                        continue

                    if overwrite in RequestsParams.PUT_NEXT_OVERWRITES_NEWER or \
                        overwrite in RequestsParams.PUT_NEXT_OVERWRITES_DIFF_SIZE:
                        stat = fpath.stat()

                        will_accept = False

                        if overwrite in RequestsParams.PUT_NEXT_OVERWRITES_NEWER:
                            log.d("Overwrite policy is NEWER, checking mtime")
                            will_accept = will_accept or is_newer(fmtime, stat.st_mtime_ns)

                        if overwrite in RequestsParams.PUT_NEXT_OVERWRITES_DIFF_SIZE:
                            log.d("Overwrite policy is SIZE, checking size")
                            will_accept = will_accept or stat.st_size != fsize

                        if will_accept:
                            log.d("Will accept file")
                        else:
                            skip_transfer()
                            continue

                    elif overwrite == RequestsParams.PUT_NEXT_OVERWRITE_YES:
                        log.d("Overwrite policy is YES, overwriting it unconditionally")

                    elif overwrite == RequestsParams.PUT_NEXT_OVERWRITE_NO:
                        log.d("Overwrite policy is NO, skipping it")
                        skip_transfer()
                        continue

                # Before accept it for real, try to open the file.
                # At least we are able to detect any error (e.g. perm denied)
                # before say the the that the transfer is began.

                fd = None

                if not preview:
                    # If it's just a preview don't try to open the file for real
                    log.d(f"Trying to open {fpath} before initializing transfer")

                    try:
                        fd = fpath.open("wb")
                        log.d(f"Able to open file: {fpath}")
                    except Exception as exc:
                        if isinstance(exc, FileNotFoundError):
                            self._send_response(self._create_error_response(
                                ServerErrors.NOT_EXISTS, q(fname))
                            )
                            continue

                        if isinstance(exc, PermissionError):
                            self._send_response(self._create_error_response(
                                ServerErrors.PERMISSION_DENIED, q(fname))
                            )
                            continue

                        if isinstance(exc, OSError):
                            self._send_response(self._create_error_response(
                                ServerErrors.GENERAL_ERROR, os_error_str(exc), q(fname))
                            )
                            continue

                        self._send_response(self._create_error_response(
                            ServerErrors.GENERAL_ERROR, exc, q(fname))
                        )
                        continue

                self._send_response(create_success_response({
                    ResponsesParams.PUT_NEXT_STATUS:
                        ResponsesParams.PUT_NEXT_STATUS_ACCEPTED,
                    ResponsesParams.PUT_NEXT_ALREADY_EXISTS: already_exists
                }))

                return fpath, fsize, fmtime, fd

        while True:
            log.d("Blocking and waiting for a file to handle...")

            # Recv files until the incomings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = put_next()

            if next_incoming is None:
                log.i("No more files: transfer completed")
                break

            incoming_fpath, incoming_size, incoming_mtime, local_fd = next_incoming

            if preview:
                log.i("Just a preview, not transferring file for real")
                # Don't transfer, just a preview
                continue

            log.i(f"Next incoming file to handle: {incoming_fpath}")

            # OK - report it
            print(f"[{self._client.tag}] put '{incoming_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")


            # File is already opened

            # TODO:
            #  if something about IO goes wrong all the transfer is compromised
            #  since we can't tell the user about it.
            #  Open is already done so there should be no permissions problems

            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_size:
                readlen = min(incoming_size - cur_pos, BEST_BUFFER_SIZE)

                # Read from the remote
                log.h(f"Waiting a chunk of {readlen}B")
                chunk = transfer_socket.recv(readlen)

                if not chunk:
                    # EOF
                    log.i(f"Finished to handle: {incoming_fpath}")
                    break

                log.h(f"Received chunk of {len(chunk)}B")
                cur_pos += len(chunk)

                if check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                local_fd.write(chunk)

                log.h(f"{cur_pos}/{incoming_size}")

                # time.sleep(0.5)

            log.i(f"Closing file {incoming_fpath}")
            local_fd.close()

            # Adjust the mtime based on the remote
            log.d(f"Setting mtime = {incoming_mtime}")
            set_mtime(incoming_fpath, incoming_mtime, round_up=True)

            # Eventually do CRC check
            if check:
                # CRC check on the received bytes
                expected_crc = btoi(transfer_socket.recv(4))
                if expected_crc != crc:
                    log.e(f"Wrong CRC; transfer failed. expected={expected_crc} | written={crc}")
                    errors.append(create_error_of_response(ServerErrors.PUT_CHECK_FAILED,
                                                           *self._qspathify(incoming_fpath)))
                    break
                else:
                    log.d("CRC check: OK")

                # Length check on the written file
                written_size = incoming_fpath.stat().st_size
                if written_size != incoming_size:
                    log.e(f"File length mismatch; transfer failed. expected={incoming_size} ; written={written_size}")
                    errors.append(create_error_of_response(ServerErrors.PUT_CHECK_FAILED,
                                                           *self._qspathify(incoming_fpath)))

                    break
                else:
                    log.d("File length check: OK")

        log.i("PUT finished")

        compute_sync_table()

        sync_rm_oks = []
        sync_rm_errs = []

        if sync_table:
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

                p = Path(path_str)

                err = None
                if not preview: # don't remove for real if it's a preview
                    err = self._rm(p)

                if not err:
                    # Removal OK
                    # TODO leading / maybe
                    sync_rm_oks.append(str(self._spath_rel_to_root_of_fpath(p)))
                else:
                    sync_rm_errs.append(err)

                cur_del_path_str = path_str


        resp_data = {
            ResponsesParams.PUT_OUTCOME: outcome
        }

        if errors:
            resp_data[ResponsesParams.PUT_ERRORS] = errors

        if sync_table:
            resp_data[ResponsesParams.PUT_SYNC_OKS] = sync_rm_oks
            resp_data[ResponsesParams.PUT_SYNC_ERRORS] = sync_rm_errs

        return create_success_response(resp_data)

    def _create_error_response(self,
                               err: Union[str, int, Dict, List[Dict]] = None,
                               *subjects  # if a subject is a Path,
                                          # must be a FPath (relative to the file system)
                               ):
        """
        Create an error response sanitizing  subjects so that they are
        Path  relative to the sharing root (spath).
        """

        log.d(f"_create_error_response of subjects {subjects}")

        if self._connected_to_sharing:
            # Sanitize paths - relative to the sharing root (don't expose internal path)
            return create_error_response(err, *self._qspathify(*subjects))

        # Subjects (if any) should not contain sharing paths, classical error response
        return create_error_response(err, *subjects)


    def _qspathify(self, *fpaths_or_strs) -> List[str]:
        """
        Adds quootes (") the string representation of every parameter, making
        those Path relative to the sharing root (spath) if are instance of Path.
        """
        # quote the spaths of fpaths
        if not fpaths_or_strs:
            return []

        log.d(f"_qspathify of {fpaths_or_strs}")

        qspathified = [
            # leave str as str
            q(self._spath_rel_to_root_of_fpath(o)) if isinstance(o, Path) else str(o)
            for o in fpaths_or_strs
        ]

        log.d(f"qspathified -> {qspathified}")

        return qspathified


    def _spath_rel_to_rcwd_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the current rcwd.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d(f"spath_of_fpath_rel_to_rcwd for p: {p}")

        fp = self._as_path(p)
        log.d(f"-> fp: {fp}")

        if self._current_sharing.ftype == FTYPE_FILE:
            if fp != self._current_sharing.path:
                raise ValueError("Invalid path for file sharing")

            log.d("Providing sharing name since ftype == FILE")
            return Path(self._current_sharing.name)

        # DIR (standard case)
        return fp.relative_to(self._current_rcwd_fpath)

    def _spath_rel_to_root_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the sharing root.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d(f"spath_of_fpath_rel_to_root for p: {p}")
        fp = self._as_path(p)
        log.d(f"-> fp: {fp}")

        if self._current_sharing.ftype == FTYPE_FILE:
            if fp != self._current_sharing.path:
                raise ValueError("Invalid path for file sharing")

            log.d("Providing sharing name since ftype == FILE")
            return Path(self._current_sharing.name)


        # DIR (standard case)
        return Path("/") / fp.relative_to(self._current_sharing.path)


    def _is_fpath_allowed(self, p: Union[str, FPath]) -> bool:
        """
        Checks whether p belongs to (is a subdirectory/file of) this sharing.
        """
        try:
            spath_from_root = self._spath_rel_to_root_of_fpath(p)
            log.d(f"Path is allowed for this sharing. spath is: {spath_from_root}")
            return True
        except:
            log.wexception(f"Path is not allowed for this sharing: {p}")
            return False


    def _fpath_joining_rcwd_and_spath(self, p: Union[str, SPath]) -> FPath:
        """
        Joins p to the current rcwd and returns an fpath
        (absolute Path from the file system root).
        If p is relative, than rcwd / p is the result.
        If p is absolute, than sharing root / p  is the result
        """
        p = self._as_path(p)

        if p.is_absolute():
            # Absolute is considered relative to the sharing root
            # Join all the path apart from the leading "/"
            fp = self._current_sharing.path.joinpath(*p.parts[1:])
        else:
            # Relative is considered relative to the current working directory
            # Join all the path
            fp = self._current_rcwd_fpath / p

        return fp.resolve()

    @classmethod
    def _as_path(cls, p: Union[str, Path]):
        if is_str(p):
            p = Path(p)

        if not isinstance(p, Path):
            raise TypeError(f"expected str or Path, found {type(p)}")

        return p
