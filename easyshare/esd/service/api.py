import mmap
import os
import subprocess
import threading
import time
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Callable, Optional, Union, Tuple, BinaryIO, Set

from ptyprocess import PtyProcess

from easyshare.auth import Auth
from easyshare.common import TransferDirection, TransferProtocol, BEST_BUFFER_SIZE, APP_VERSION
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, ClientContext
from easyshare.esd.daemons.api import get_api_daemon
from easyshare.logging import get_logger
from easyshare.protocol.requests import Request, is_request, Requests, RequestParams, RequestsParams
from easyshare.protocol.responses import create_error_response, ServerErrors, Response, create_success_response, \
    create_error_of_response, TransferOutcomes, ResponsesParams
from easyshare.protocol.types import ServerInfo, FTYPE_DIR, RexecEventType, create_file_info, FTYPE_FILE, FileType
from easyshare.sockets import SocketTcp
from easyshare.ssl import get_ssl_context
from easyshare.streams import StreamClosedError
from easyshare.styling import green, red
from easyshare.tracing import get_tracing_level, TRACING_TEXT, trace_text
from easyshare.utils.json import btoj, jtob, j
from easyshare.utils.os import is_unix, ls, os_error_str, tree, cp, mv, rm, run_detached, get_passwd, pty_detached, find
from easyshare.utils.path import is_hidden
from easyshare.utils.str import q
from easyshare.utils.types import is_str, is_list, is_bool, is_valid_list, stob, itob, btos, btoi, is_int

log = get_logger(__name__)


# SPath and FPath are Path with a different semantic:
SPath = Path # sharing path, is relative and bounded to the sharing domain
FPath = Path # file system path, absolute, starts from the server's file system root

class ApiService:
    def __init__(self, *,
                 sharings: List[Sharing],
                 name: str,
                 auth: Auth,
                 rexec: bool):
        super().__init__()
        self._sharings = {s.name: s for s in sharings}
        self._name = name
        self._auth = auth
        self._rexec_enabled = rexec

        self._clients_lock = threading.Lock()
        self._clients: Dict[Endpoint, ClientHandler] = {}

        get_api_daemon().add_callback(self._handle_new_connection)

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

    def _handle_new_connection(self, sock: SocketTcp) -> bool:
        log.i("Received new client connection from %s", sock.remote_endpoint())
        self._add_client(sock)
        return True  # handled


    def _add_client(self, client_sock: SocketTcp):
        client = ClientContext(client_sock)
        client_handler = ClientHandler(client, self)
        log.i("Adding client %s", client)
        # no need to lock, still in single thread execution
        self._clients[client.endpoint] = client_handler

        th = threading.Thread(target=client_handler.handle)
        th.start()

        pass



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
        if not handler._api_service.is_rexec_enabled():
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
            log.e("Forbidden: command allowed only for DIR sharing by [%s]", handler._client)
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
            log.e("Forbidden: write action on read only sharing by [%s]", handler._client)
            return handler._create_error_response(ServerErrors.NOT_WRITABLE)
        return api(handler, params)

    return require_write_permission_wraper


class ClientHandler:

    def __init__(self, client: ClientContext, api_service: ApiService):
        self._api_service = api_service

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
            Requests.REXEC: self._rexec,
            Requests.RSHELL: self._rshell,
            Requests.RCD: self._rcd,
            Requests.RPWD: self._rpwd,
            Requests.RLS: self._rls,
            Requests.RTREE: self._rtree,
            Requests.RFIND: self._rfind,
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
        log.i("Handling client %s", self._client)

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
                        log.exception("Exception occurred while handling request")
                        resp_payload = self._create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

                else:
                    log.e("Invalid request - discarding it")
                    resp_payload = self._create_error_response(ServerErrors.INVALID_REQUEST)

                self._send_response(resp_payload)
            except StreamClosedError:
                pass # self._client.stream.is_open() will fail next iter
            except:
                log.exception("Unexpected exception occurred")
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

        log.i("Connection closed with client %s", self._client)

        print(red(f"[{self._client.tag}] disconnected "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))


    def _recv_json(self) -> Dict:
        req_payload_data = self._client.stream.read(trace=False)
        req_payload = None

        try:
            req_payload = btoj(req_payload_data)
        except:
            log.exception("Failed to parse payload - discarding it")

        # Trace IN
        if get_tracing_level() == TRACING_TEXT: # check for avoid json_pretty_str call
            trace_text(
                j(req_payload),
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
        if get_tracing_level() == TRACING_TEXT: # check for avoid json_pretty_str call
            trace_text(
                j(response),
                sender=self._client.socket.endpoint(), receiver=self._client.socket.remote_endpoint(),
                direction=TransferDirection.OUT, protocol=TransferProtocol.TCP
            )

        # Really send it back
        self._client.stream.write(jtob(response), trace=False) # don't trace at byte level


    # == SERVER COMMANDS ==

    def _connect(self, params: RequestParams) -> Response:
        log.i("<< CONNECT  |  %s", self._client)

        password = params.get("password")

        if self._connected_to_server:
            log.w("Client already connected")
            return create_success_response()

        # Authentication
        log.i("Authentication check - type: %s", self._api_service.auth().algo_type())

        # Just ask the auth whether it matches or not
        # (The password can either be none/plain/hash, the auth handles them all)
        if not self._api_service.auth().authenticate(password):
            log.e("Authentication FAILED")
            return self._create_error_response(ServerErrors.AUTHENTICATION_FAILED)
        else:
            log.i("Authentication OK")

        self._connected_to_server = True

        print(f"[{self._client.tag}] connect {'*' * len(password) if password else ''}"
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response()

    @require_server_connection
    def _disconnect(self, _: RequestParams):
        log.i("<< DISCONNECT  |  %s", self._client)

        if not self._connected_to_server:
            log.w("Already disconnected")

        self._connected_to_server = False

        print((f"[{self._client.tag}] disconnect "
               f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))

        return create_success_response()

    def _list(self, _: RequestParams):
        log.i("<< LIST  |  %s", self._client)

        print(f"[{self._client.tag}] list "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(
            [sh.info() for sh in self._api_service.sharings().values()])

    def _info(self, _: RequestParams):
        log.i("<< INFO  |  %s", self._client)

        print(f"[{self._client.tag}] info "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(self._api_service.server_info())

    def _ping(self, _: RequestParams):
        log.i("<< PING  |  %s", self._client)

        print(f"[{self._client.tag}] ping "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        time.sleep(4)

        return create_success_response("pong")


    @require_server_connection
    @require_unix
    @require_rexec_enabled
    def _rexec(self, params: RequestParams):
        cmd = params.get(RequestsParams.REXEC_CMD)
        if not cmd:
            self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< REXEC %s  |  %s", cmd, self._client)

        # OK - report it
        print(f"[{self._client.tag}] rexec '{cmd}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        self._send_response(create_success_response())

        def out_hook(text: str):
            log.d("> %s", text)
            self._client.stream.write(
                RexecEventType.TEXT_B + stob(text), trace=True
            )

        def end_hook(retcode: int):
            log.d("END %d", retcode)
            self._client.stream.write(
                RexecEventType.RETCODE_B + itob(retcode % 255, length=1),
                trace=True
            )

        def stdin_receiver(process: subprocess.Popen):
            while True:
                in_b = self._client.stream.read(trace=True)
                event_type: int = in_b[0]
                log.d("Event type = %d", event_type)

                if event_type == RexecEventType.TEXT:
                    text = btos(in_b[1:])
                    log.d("< %s", text)
                    process.stdin.write(text)
                    process.stdin.flush()
                elif event_type == RexecEventType.EOF:
                    log.d("< EOF")
                    process.stdin.close()
                elif event_type == RexecEventType.KILL:
                    log.d("< KILL")
                    process.terminate()
                elif event_type == RexecEventType.ENDACK:
                    log.d("< ENDACK")
                    break
                else:
                    log.w("Can't handle event of type %d", event_type)

        # Bind server stdout/stderr and send those to client
        proc, out_th = run_detached(
            cmd,
            stdout_hook=out_hook,
            stderr_hook=out_hook,
            end_hook=end_hook
        )

        # Receive stdin from client
        stdin_th = threading.Thread(target=stdin_receiver, args=(proc, ))
        stdin_th.start()

        # Wait everybody
        stdin_th.join()
        out_th.join()

        if proc.returncode is not None:
            log.d("REXEC finished with return code = %d", proc.returncode)
        else:
            log.w("REXEC invalid return code")

    @require_server_connection
    @require_unix
    @require_rexec_enabled
    def _rshell(self, params: RequestParams):
        cmd = params.get(RequestsParams.RSHELL_CMD)
        if not cmd:
            cmd = get_passwd().pw_shell

        log.i("<< RSHELL %s  |  %s", cmd, self._client)

        # OK - report it
        print(f"[{self._client.tag}] rshell '{cmd}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        self._send_response(create_success_response())

        def out_hook(text: str):
            log.d("> %s", text)
            self._client.stream.write(
                RexecEventType.TEXT_B + stob(text), trace=True
            )

        def end_hook(retcode: int):
            log.d("END %d", retcode)
            self._client.stream.write(
                RexecEventType.RETCODE_B + itob(retcode % 255, length=1),
                trace=True
            )

        def stdin_receiver(ptyprocess: PtyProcess):
            while True:
                in_b = self._client.stream.read(trace=True)
                event_type: int = in_b[0]
                log.d("Event type = %d", event_type)

                if event_type == RexecEventType.TEXT:
                    text = btos(in_b[1:])
                    log.d("< %s", text)
                    ptyprocess.write(text)
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
                    log.w("Can't handle event of type %d", event_type)

        ptyproc = pty_detached(
            out_hook=out_hook,
            end_hook=end_hook,
            cmd=cmd
        )

        # Receive stdin from client
        stdin_th = threading.Thread(target=stdin_receiver, args=(ptyproc, ))
        stdin_th.start()

        # Wait everybody
        stdin_th.join()
        ptyproc.wait()

        log.d("RSHELL finished")

    @require_server_connection
    def _open(self, params: RequestParams):
        sharing_name = params.get(RequestsParams.OPEN_SHARING)

        if not sharing_name:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        sharing: Sharing = self._api_service.sharings().get(sharing_name)

        if not sharing:
            return self._create_error_response(ServerErrors.SHARING_NOT_FOUND, q(sharing_name))

        log.i("<< OPEN %s |  %s", sharing_name, self._client)

        print(f"[{self._client.tag}] open '{sharing.name}'"
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        self._connected_to_sharing = True
        self._current_sharing = sharing
        self._current_rcwd_fpath = sharing.path

        return create_success_response()

    # == SHARING COMMANDS ==

    @require_sharing_connection
    def _close(self, _: RequestParams):
        log.i("<< CLOSE  |  %s", self._client)

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

        if not is_str(spath):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RCD %s  |  %s", spath, self._client)

        new_rcwd_fpath = self._fpath_joining_rcwd_and_spath(spath)

        log.d("Would cd into: %s", new_rcwd_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(new_rcwd_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(spath))

        # Check if it actually exists
        if not new_rcwd_fpath.is_dir():
            return self._create_error_response(ServerErrors.NOT_A_DIRECTORY, new_rcwd_fpath)

        # The path is allowed and exists, setting it as new rcwd
        self._current_rcwd_fpath = new_rcwd_fpath

        log.i("New valid rcwd: %s", self._current_rcwd_fpath)

        # Tell the client the new rcwd
        rcwd_spath_str = str(self._current_rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        log.d("RCWD for the client: %s", rcwd_spath_str)

        print(f"[{self._client.tag}] rcd '{self._current_rcwd_fpath}' "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(rcwd_spath_str)

    @require_sharing_connection
    @require_d_sharing
    def _rpwd(self, _: RequestParams) -> Response:
        log.i("<< RPWD  |  %s", self._client)

        rcwd_spath_str = str(self._current_rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        print(f"[{self._client.tag}] rpwd "
              f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

        return create_success_response(rcwd_spath_str)


    @require_sharing_connection
    @require_d_sharing
    def _rls(self, params: RequestParams):

        path = params.get(RequestsParams.RLS_PATH) or "."
        sort_by = params.get(RequestsParams.RLS_SORT_BY) or ["name"]
        reverse = params.get(RequestsParams.RLS_REVERSE) or False
        hidden = params.get(RequestsParams.RLS_HIDDEN) or False
        details = params.get(RequestsParams.RLS_DETAILS) or False

        if not is_str(path) or not is_list(sort_by, str) or not is_bool(reverse) \
            or not is_bool(hidden) or not is_bool(details):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RLS %s %s%s  |  %s",
              path, sort_by,
              " reverse " if reverse else "",
              self._client)

        ls_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d("Would ls into: %s", ls_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(ls_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i("Going to ls on valid path %s", ls_fpath)

        try:
            ls_result = ls(ls_fpath,
                           sort_by=sort_by, reverse=reverse,
                           hidden=hidden, details=details)
            # OK - report it
            print(f"[{self._client.tag}] rls '{ls_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except FileNotFoundError:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.NOT_EXISTS,
                                               ls_fpath)
        except PermissionError:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.PERMISSION_DENIED,
                                               ls_fpath)
        except OSError as oserr:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               os_error_str(oserr),
                                               ls_fpath)
        except Exception as exc:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               exc,
                                               ls_fpath)

        log.i("RLS response %s", str(ls_result))

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

        if not is_str(path) or not is_list(sort_by, str) or not is_bool(reverse) \
            or not is_bool(details):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)


        log.i("<< RTREE %s %s%s  |  %s",
              path, sort_by,
              " reverse " if reverse else "",
              self._client)

        tree_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d("Would tree into: %s", tree_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(tree_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i("Going to tree on valid path %s", tree_fpath)

        try:
            tree_root = tree(tree_fpath,
                             sort_by=sort_by, reverse=reverse,
                             hidden=hidden, max_depth=max_depth,
                             details=details)
            # OK - report it
            print(f"[{self._client.tag}] rtree '{tree_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except FileNotFoundError:
            log.exception("rtree exception occurred")
            return self._create_error_response(ServerErrors.NOT_EXISTS,
                                               tree_fpath)
        except PermissionError:
            log.exception("rtree exception occurred")
            return self._create_error_response(ServerErrors.PERMISSION_DENIED,
                                               tree_fpath)
        except OSError as oserr:
            log.exception("rtree exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               os_error_str(oserr),
                                               tree_fpath)
        except Exception as exc:
            log.exception("rtree exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               exc,
                                               tree_fpath)

        log.i("RTREE response %s", j(tree_root))

        return create_success_response(tree_root)


    @require_sharing_connection
    @require_d_sharing
    def _rfind(self, params: RequestParams):
        path = params.get(RequestsParams.RFIND_PATH) or "."
        name = params.get(RequestsParams.RFIND_NAME)
        regex = params.get(RequestsParams.RFIND_REGEX)
        case_sensitive = params.get(RequestsParams.RFIND_CASE_SENSITIVE)
        ftype = params.get(RequestsParams.RFIND_FTYPE)
        details = params.get(RequestsParams.RFIND_DETAILS) or False

        if case_sensitive is None:
            case_sensitive = True

        if not is_str(path) or \
                (name and not is_str(name)) or \
                (regex and not is_str(regex)) or \
                (not is_bool(case_sensitive)) or \
                ftype not in [None, FTYPE_DIR, FTYPE_FILE]:
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RFIND %s  |  %s", path, self._client)

        find_fpath = self._fpath_joining_rcwd_and_spath(path)
        log.d("Would find into: %s", find_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(find_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(path))

        log.i("Going to find on valid path %s", find_fpath)

        try:
            find_result = find(find_fpath,
                               name=name,
                               regex=regex,
                               case_sensitive=case_sensitive,
                               ftype=ftype,
                               details=details,
                               file_info_name_provider=lambda p: str(self._spath_rel_to_rcwd_of_fpath(p)))

            # OK - report it
            print(f"[{self._client.tag}] rfind '{find_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except FileNotFoundError:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.NOT_EXISTS,
                                               find_fpath)
        except PermissionError:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.PERMISSION_DENIED,
                                               find_fpath)
        except OSError as oserr:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               os_error_str(oserr),
                                               find_fpath)
        except Exception as exc:
            log.exception("rls exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               exc,
                                               find_fpath)

        log.i("RFIND response %s", str(find_result))

        return create_success_response(find_result)


    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rmkdir(self, params: RequestParams):
        directory = params.get(RequestsParams.RMKDIR_PATH)

        if not is_str(directory):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)


        log.i("<< RMKDIR %s  |  %s", directory, self._client)

        directory_fpath = self._fpath_joining_rcwd_and_spath(directory)
        log.d("Would create directory: %s", directory_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(directory_fpath):
            return self._create_error_response(ServerErrors.INVALID_PATH, q(directory))

        log.i("Going to mkdir on valid path %s", directory_fpath)

        try:
            directory_fpath.mkdir(parents=True)
            # OK - report it
            print(f"[{self._client.tag}] rmkdir '{directory_fpath}' "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")
        except PermissionError:
            log.exception("rmkdir exception occurred")
            return self._create_error_response(ServerErrors.PERMISSION_DENIED,
                                               directory_fpath)
        except FileExistsError:
            log.exception("rmkdir exception occurred")
            return self._create_error_response(ServerErrors.DIRECTORY_ALREADY_EXISTS,
                                               directory_fpath)
        except OSError as oserr:
            log.exception("rmkdir exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               os_error_str(oserr),
                                               directory_fpath)
        except Exception as exc:
            log.exception("rmkdir exception occurred")
            return self._create_error_response(ServerErrors.ERR_2,
                                               exc,
                                               directory_fpath)

        return create_success_response()

    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _rrm(self, params: RequestParams):

        paths = params.get(RequestsParams.RRM_PATHS)

        if not is_valid_list(paths, str):
            return self._create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RRM %s  |  %s", paths, self._client)

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

        log.i("RM '%s'", path)

        error = None

        def handle_rm_error(exc: Exception, p: Path):
            nonlocal error

            if isinstance(exc, PermissionError):
                error = create_error_of_response(ServerErrors.RM_PERMISSION_DENIED,
                                                 *self._qspathify(p))
            elif isinstance(exc, FileNotFoundError):
                error = create_error_of_response(ServerErrors.RM_NOT_EXISTS,
                                                 *self._qspathify(p))
            elif isinstance(exc, OSError):
                error = create_error_of_response(ServerErrors.RM_OTHER_ERROR,
                                                 os_error_str(exc),
                                                 *self._qspathify(p))
            else:
                error = create_error_of_response(ServerErrors.RM_OTHER_ERROR,
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
            if isinstance(exc, PermissionError):
                log.exception("rcp exception occurred")
                errors.append(create_error_of_response(ServerErrors.CP_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                log.exception("rcp exception occurred")
                errors.append(create_error_of_response(ServerErrors.CP_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                log.exception("rcp exception occurred")
                errors.append(create_error_of_response(ServerErrors.CP_OTHER_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                log.exception("rcp exception occurred")
                errors.append(create_error_of_response(ServerErrors.CP_OTHER_ERROR,
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
            if isinstance(exc, PermissionError):
                log.exception("rmv exception occurred")
                errors.append(create_error_of_response(ServerErrors.MV_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                log.exception("rmv exception occurred")
                errors.append(create_error_of_response(ServerErrors.MV_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                log.exception("rmv exception occurred")
                errors.append(create_error_of_response(ServerErrors.MV_OTHER_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                log.exception("rmv exception occurred")
                errors.append(create_error_of_response(ServerErrors.MV_OTHER_ERROR,
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
                log.e("'%s' must be an existing directory", destination_fpath)
                return self._create_error_response(ServerErrors.NOT_A_DIRECTORY, destination_fpath)


        log.i("<< %s %s %s  |  %s",
              primitive_name.upper(), sources, destination, self._client)

        for source_path in sources:
            source_fpath = self._fpath_joining_rcwd_and_spath(source_path)

            # Path validity check
            if self._is_fpath_allowed(source_fpath):
                try:
                    log.i("%s %s -> %s", primitive_name, source_fpath, destination_fpath)
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

        log.i("<< GET %s  |  %s", paths, self._client)

        self._send_response(create_success_response())

        # TODO: use a secondary socket?
        transfer_socket = self._client.socket

        # Next file/directory to serve
        next_servings: List[Tuple[FPath, FPath, str]] = [] # fpath, basedir, prefix

        errors = []
        outcome = TransferOutcomes.SUCCESS

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
            # "*" means get everything inside the rcwd without wrapping it into a folder
            log.d("f = %s", f)

            p = Path(f)

            take_all_unwrapped = True if (p.parts and p.parts[len(p.parts) - 1]) == "*" else False

            log.d("is * = %s", take_all_unwrapped)

            if take_all_unwrapped:
                # Consider the path without the last *
                p = p.parent

            log.d("p(f) = %s", p)

            # Compute the absolute path depending on the user request (p)
            # and our current rcwd
            fpath = self._fpath_joining_rcwd_and_spath(p)

            is_root = fpath == self._current_sharing.path
            log.d("is root = %s", is_root)

            # Compute the basedir: the directory from which the user takes
            # the files (this will have effect on the location of the files on
            # the client)
            # If the last component is a *, consider the entire content of the folder (unwrapped)
            # Otherwise the basedir is the parent (so that the folder will be wrapped)

            prefix = ""

            if take_all_unwrapped:
                basedir = fpath
            else:
                if is_root: # don't go outside "."
                    basedir = fpath
                    prefix = self._current_sharing.name
                else:
                    basedir = fpath.parent

            log.d("fpath(f)         = %s", fpath)
            log.d("basedir(f)  = %s", basedir)
            log.d("prefix = %s", self._current_sharing.name)

            # Do domain check now, after this check it should not be
            # necessary to check it since we can only go deeper

            if self._is_fpath_allowed(fpath) and self._is_fpath_allowed(basedir):
                next_servings.append((fpath, basedir, prefix))
            else:
                log.e("Path %s is invalid (out of sharing domain)", f)
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
                req = self._recv_json()

                if not req:
                    self._send_response(self._create_error_response(ServerErrors.INVALID_REQUEST))
                    continue

                if len(next_servings) == 0:
                    log.i("No more files: transfer completed. Sending END")
                    self._send_response(create_success_response())
                    break

                next_transfer = handle_get_next_request(req)

            # Either next_transfer is valid or we have finished
            return next_transfer

        def handle_get_next_request(req: Dict) -> Union[Tuple[FPath, BinaryIO], None]: # fpath, fd
            while True:
                action = req.get(RequestsParams.GET_NEXT_ACTION)
                if action not in RequestsParams.GET_NEXT_ACTIONS:
                    log.w("Unknown action: %s", action)
                    action = RequestsParams.GET_NEXT_ACTION_SEEK

                log.i("<< GET_NEXT action = %s", action)

                # 2. Serve the file
                # -> send response to the client anyway
                # -> return only if there is a file to transfer

                # Get next file (or dir)
                # Do not pop it now: either transfer os skip must be specified
                # for a regular file before being popped out
                # (In this way we can handle cases in which the client don't
                # want to receive the file (because of overwrite, or anything else)
                next_fpath, next_basedir, next_prefix = next_servings[len(next_servings) - 1]

                log.d("Next file fpath: %s", next_fpath)
                log.d("Next file basedir: %s", next_basedir)

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

                log.d("Next file spath: %s", next_spath_str)

                # Check if it's hidden

                if no_hidden and is_hidden(next_fpath):
                    log.d("Not sending %s since no_hidden is True", next_fpath)
                    next_servings.pop()
                    continue

                finfo = create_file_info(
                    next_fpath,
                    name=next_spath_str
                )

                # Case: FILE
                if finfo and next_fpath.is_file():
                    next_transfer = None

                    log.i("NEXT FILE: %s", next_fpath)

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
                                log.d("Able to open file: %s", next_fpath)

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
                                    create_error_response(ServerErrors.ERR_2,
                                                          os_error_str(oserr),
                                                          q(next_spath_str))
                                )
                                return None
                            except Exception as exc:
                                log.w("Can't open file - not transferring file")
                                self._send_response(
                                    create_error_response(ServerErrors.ERR_2,
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
                    log.i("NEXT DIR: %s", next_fpath)

                    # Pop it now; it doesn't make sense ask the user whether
                    # skip or overwrite as for files
                    next_servings.pop()

                    # Directory found
                    try:
                        dir_files: List[FPath] = list(next_fpath.iterdir())
                    except FileNotFoundError:
                        errors.append(create_error_of_response(ServerErrors.NOT_EXISTS,
                                                               q(next_spath_str)))
                        continue
                    except PermissionError:
                        errors.append(create_error_of_response(ServerErrors.PERMISSION_DENIED,
                                                               q(next_spath_str)))
                        continue
                    except OSError as oserr:
                        errors.append(create_error_of_response(ServerErrors.ERR_2,
                                                                 os_error_str(oserr),
                                                                 q(next_spath_str)))
                        continue
                    except Exception as exc:
                        errors.append(create_error_of_response(ServerErrors.ERR_2,
                                                                 exc,
                                                                 q(next_spath_str)))
                        continue

                    if dir_files:
                        log.i("Found a filled directory: adding all inner files to remaining_files")
                        for file_in_dir in dir_files:
                            log.i("Adding %s", file_in_dir)
                            next_servings.append((file_in_dir, next_basedir, prefix))
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
                    log.w("Not file nor dir? skipping %s", next_fpath)
                    errors.append(create_error_of_response(ServerErrors.TRANSFER_SKIPPED,
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

            log.i("Next outgoing file to handle: %s", next_transf_fpath)

            # OK - report it
            print(f"[{self._client.tag}] get '{next_transf_fpath}'"
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")

            file_len = next_transf_fpath.stat().st_size

            # File is already opened
            source = next_transf_f

            if use_mmap:
                try:
                    # try to mmap the file to memory
                    source = mmap.mmap(next_transf_f.fileno(), 0,
                                       prot=mmap.PROT_READ)
                except:
                    log.w("mmap failed, will read directly from file")

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
                    log.i("Finished to handle: %s", next_transf_fpath)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                log.d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

                transfer_socket.send(chunk)

            log.i("Closing file %s", next_transf_fpath)
            next_transf_f.close()
            if source != next_transf_f:
                source.close() # mmap

            # Eventually send the CRC in-band
            if check:
                log.d("Sending CRC: %d", crc)
                transfer_socket.send(itob(crc, 4))

        log.i("GET finished")

        resp_data = {
            ResponsesParams.GET_OUTCOME: outcome
        }

        if errors:
            resp_data[ResponsesParams.GET_ERRORS] = errors

        return create_success_response(resp_data)



    @require_sharing_connection
    @require_d_sharing
    @require_write_permission
    def _put(self, params: RequestParams):
        check = params.get(RequestsParams.PUT_CHECK)
        sync = params.get(RequestsParams.PUT_SYNC)

        # Hidden

        log.i("<< PUT  |  %s", self._client)

        self._send_response(create_success_response())

        # TODO: use a secondary socket?
        transfer_socket = self._client.socket

        errors = []
        outcome = TransferOutcomes.SUCCESS

        sync_table: Optional[Dict[str, None]] = None

        def compute_sync_table(fpath: FPath, ftype: FileType):
            nonlocal sync_table

            if sync_table:
                log.e("Sync table already initialized, only a directory/file can be pushed with --sync")
                # TODO: raise exception known (instead of command exec failed)...
                raise ValueError("Sync table already initialized, "
                                 "only a directory/file can be pushed with --sync")

            up_path = fpath if ftype == FTYPE_DIR else fpath.parent
            log.d("SYNC Up path: '%s'", up_path)

            findings = find(up_path)
            # Preserve order for perform RM in optimal order (parents first)
            sync_table = OrderedDict({f.get("name"): None for f in findings})
            log.d("SYNC computed old_files table\n%s",
                  "\n".join(sync_table.keys()))


        def put_next():

            while True:
                log.d("Waiting for next() request from client...")

                # 1. Receive the request from the client

                # e.g. {file: {name: f1, size: 293}, overwrite: "..."} // client doesn't provide the path
                req = self._recv_json()

                # File info
                finfo = req.get(RequestsParams.PUT_NEXT_FILE)

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

                log.i("<< PUT_NEXT %s", j(finfo))

                fpath = self._fpath_joining_rcwd_and_spath(fname)

                if not self._is_fpath_allowed(fpath):
                    log.e("Path %s is invalid (out of sharing domain)", fpath)
                    self._send_response(self._create_error_response(
                        ServerErrors.INVALID_PATH, q(fname))
                    )
                    continue

                log.d("Sharing domain check OK")

                # If sync is True track the files in the current directory
                # so that we can remove old files (the one for which no file info
                # is retrieved from the server) after the transfer completes.
                if sync:
                    # Only the first push determinates the directory the be pushed
                    # (Therefore the client have to send the finfo of the root folder first)
                    if not sync_table:
                        compute_sync_table(fpath, ftype)

                    # Remove from the SYNC table eventually
                    # Do the removal for each possible path within local_path
                    # (so that we won't delete parent folder if the change is
                    # inside the children)
                    incremental_path = Path.cwd()
                    for part in fpath.parts:
                        incremental_path = incremental_path / part
                        incremental_path_str = str(incremental_path)
                        log.d("Removing from SYNC table: '%s'", incremental_path_str)
                        sync_table.pop(incremental_path_str, None)

                # Check whether is a dir or a file
                if ftype == FTYPE_DIR:
                    # Handle dir now by creating dirs
                    log.i("Creating dirs %s", fpath)
                    fpath.mkdir(parents=True, exist_ok=True)
                    self._send_response(create_success_response({
                        ResponsesParams.PUT_NEXT_STATUS:
                            ResponsesParams.PUT_NEXT_STATUS_ACCEPTED
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
                        log.i("Creating parent dirs %s", fpath_parent)
                        fpath_parent.mkdir(parents=True, exist_ok=True)

                # Check whether it already exists
                if fpath.is_file():
                    log.w("File already exists; deciding what to do based on overwrite policy: %s",
                          overwrite)

                    # Take a decision based on the overwrite policy
                    if overwrite == RequestsParams.PUT_NEXT_OVERWRITE_PROMPT:
                        log.d("Overwrite policy is PROMPT, asking the client whether overwrite")
                        self._send_response(create_success_response({
                            ResponsesParams.PUT_NEXT_STATUS:
                                ResponsesParams.PUT_NEXT_STATUS_ALREADY_EXISTS
                        }))
                        continue

                    if overwrite == RequestsParams.PUT_NEXT_OVERWRITE_NEWER:
                        log.d("Overwrite policy is NEWER, checking mtime")
                        stat = fpath.stat()
                        if stat.st_mtime_ns >= fmtime:
                            # Our version is newer, won't accept the file
                            self._send_response(create_success_response({
                                ResponsesParams.PUT_NEXT_STATUS:
                                    ResponsesParams.PUT_NEXT_STATUS_REFUSED
                            }))
                            continue
                        else:
                            log.d("Our version is older, will accept file")

                    elif overwrite == RequestsParams.PUT_NEXT_OVERWRITE_YES:
                        log.d("Overwrite policy is YES, overwriting it unconditionally")

                # Before accept it for real, try to open the file.
                # At least we are able to detect any error (e.g. perm denied)
                # before say the the that the transfer is began.
                log.d("Trying to open file before initializing transfer")

                try:
                    fd = fpath.open("wb")
                    log.d("Able to open file: %s", fpath)
                except FileNotFoundError:
                    self._send_response(self._create_error_response(
                        ServerErrors.NOT_EXISTS, q(fname))
                    )
                    continue
                except PermissionError:
                    self._send_response(self._create_error_response(
                        ServerErrors.PERMISSION_DENIED, q(fname))
                    )
                    continue
                except OSError as oserr:
                    self._send_response(self._create_error_response(
                        ServerErrors.ERR_2, os_error_str(oserr), q(fname))
                    )
                    continue
                except Exception as exc:
                    self._send_response(self._create_error_response(
                        ServerErrors.ERR_2, exc, q(fname))
                    )
                    continue


                self._send_response(create_success_response({
                    ResponsesParams.PUT_NEXT_STATUS:
                        ResponsesParams.PUT_NEXT_STATUS_ACCEPTED
                }))

                return fpath, fsize, fd

        while True:
            log.d("Blocking and waiting for a file to handle...")

            # Recv files until the incomings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = put_next()

            if not next_incoming:
                log.i("No more files: transfer completed")
                break

            incoming_fpath, incoming_size, local_fd = next_incoming
            log.i("Next incoming file to handle: %s", incoming_fpath)

            # OK - report it
            print(f"[{self._client.tag}] put '{incoming_fpath}'"
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})")


            # File is already opened

            # TODO:
            #  if something about IO goes wrong all the transfer is compromised
            #  since we can't tell the user about it.
            #  Open is already done so there should be no permissions problems
            # The solution is to notify the client on the pyro channel, but this
            # implies that the client use an async mechanism for get (while for
            # now is synchronous)

            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_size:
                readlen = min(incoming_size - cur_pos, BEST_BUFFER_SIZE)

                # Read from the remote
                log.d("Waiting a chunk of %dB", readlen)
                chunk = transfer_socket.recv(readlen)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", incoming_fpath)
                    break

                log.d("Received chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                local_fd.write(chunk)

                log.d("%d/%d (%.2f%%)", cur_pos, incoming_size, cur_pos / incoming_size * 100)

            log.i("Closing file %s", incoming_fpath)
            local_fd.close()

            # Eventually do CRC check
            if check:
                # CRC check on the received bytes
                expected_crc = btoi(transfer_socket.recv(4))
                if expected_crc != crc:
                    log.e("Wrong CRC; transfer failed. expected=%d | written=%d",
                          expected_crc, crc)
                    errors.append(create_error_of_response(ServerErrors.PUT_CHECK_FAILED,
                                                           *self._qspathify(incoming_fpath)))
                    break
                else:
                    log.d("CRC check: OK")

                # Length check on the written file
                written_size = incoming_fpath.stat().st_size
                if written_size != incoming_size:
                    log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                          incoming_size, written_size)
                    errors.append(create_error_of_response(ServerErrors.PUT_CHECK_FAILED,
                                                           *self._qspathify(incoming_fpath)))

                    break
                else:
                    log.d("File length check: OK")

        log.i("PUT finished")

        sync_rm_oks = []
        sync_rm_errs = []

        if sync:
            # Check if there are old files to removes
            log.i("Detected %d removal to do due to sync", len(sync_table))

            # We can avoid some rm if we are deleting a parent folder
            # and sync_table contains the children.
            # Since the entries are sorted (walk_preoreder) we can iterate and skip
            # consecutive entries if they have the same prefix as the one before

            cur_del_path_str = None
            for path_str in sync_table.keys():
                if cur_del_path_str and path_str.startswith(cur_del_path_str):
                    log.d("Should remove '%s' but skipping, already deleting parent", path_str)
                    continue
                # We actually have to delete this
                log.i("Will remove '%s'", path_str)
                #
                # p = Path(path_str)
                # err = self._rm(p)
                # if not err:
                #     # Removal OK
                #     # TODO leading / maybe
                #     sync_rm_oks.append(self._spath_rel_to_root_of_fpath(p))
                # else:
                #     sync_rm_errs.append(err)

                cur_del_path_str = path_str


        resp_data = {
            ResponsesParams.PUT_OUTCOME: outcome
        }

        if errors:
            resp_data[ResponsesParams.PUT_ERRORS] = errors

        if sync:
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

        log.d("_create_error_response of subjects %s", subjects)

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

        log.d("_qspathify of %s", fpaths_or_strs)

        qspathified = [
            # leave str as str
            q(self._spath_rel_to_root_of_fpath(o)) if isinstance(o, Path) else str(o)
            for o in fpaths_or_strs
        ]

        log.d("qspathified -> %s", qspathified)

        return qspathified


    def _spath_rel_to_rcwd_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the current rcwd.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d("spath_of_fpath_rel_to_rcwd for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._current_rcwd_fpath)

    def _spath_rel_to_root_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the sharing root.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d("spath_of_fpath_rel_to_root for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._current_sharing.path)


    def _is_fpath_allowed(self, p: Union[str, FPath]) -> bool:
        """
        Checks whether p belongs to (is a subdirectory/file of) this sharing.
        """
        try:
            spath_from_root = self._spath_rel_to_root_of_fpath(p)
            log.d("Path is allowed for this sharing. spath is: %s", spath_from_root)
            return True
        except:
            log.d("Path is not allowed for this sharing: %s", p)
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