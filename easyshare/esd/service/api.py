import threading
import time
from typing import List, Dict, Callable

from easyshare.auth import Auth
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, ClientContext
from easyshare.esd.daemons.api import get_api_daemon
from easyshare.esd.service.execution.rexec import RexecService
from easyshare.logging import get_logger
from easyshare.protocol.requests import Request, is_request, Requests, RequestParams
from easyshare.protocol.responses import create_error_response, ServerErrors, Response, create_success_response
from easyshare.protocol.stream import StreamClosedError
from easyshare.protocol.types import ServerInfo
from easyshare.sockets import SocketTcp
from easyshare.ssl import get_ssl_context
from easyshare.styling import green, red
from easyshare.tracing import trace_in, trace_out, is_tracing_enabled
from easyshare.utils.json import btoj, jtob, j
from easyshare.utils.os import is_unix

log = get_logger(__name__)


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

    def sharings(self) -> List[Sharing]:
        return list(self._sharings.values())

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
            "auth": True if (self._auth and self._auth.algo_security() > 0) else False
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
def ensure_connected(api):
    def ensure_connected_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not handler._connected:
            return create_error_response(ServerErrors.NOT_CONNECTED)
        return api(handler, params)
    return ensure_connected_wrapper


# decorator
def ensure_unix(api):
    def ensure_unix_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not is_unix():
            return create_error_response(ServerErrors.SUPPORTED_ONLY_FOR_UNIX)
        return api(handler, params)
    return ensure_unix_wrapper


# decorator
def ensure_rexec_enabled(api):
    def ensure_rexec_enabled_wrapper(handler: 'ClientHandler', params: RequestParams):
        if not handler._api_service.is_rexec_enabled():
            return create_error_response(ServerErrors.REXEC_DISABLED)
        return api(handler, params)
    return ensure_rexec_enabled_wrapper


class ClientHandler:

    def __init__(self, client: ClientContext, api_service: ApiService):
        self._api_service = api_service

        self._client = client

        self._connected = None # neither "connected" nor "disconnected"

        self._request_dispatcher: Dict[str, Callable[[RequestParams], Response]] = {
            Requests.CONNECT: self._connect,
            Requests.DISCONNECT: self._disconnect,
            Requests.LIST: self._list,
            Requests.INFO: self._info,
            Requests.PING: self._ping,
            Requests.REXEC: self._rexec,
            "sleep": self._sleep
        }

    def handle(self):
        log.i("Handling client %s", self._client)

        while self._client.stream.is_open() and self._connected is not False:
            try:
                self._recv()
            except StreamClosedError:
                pass
            except:
                log.exception("Unexpected exception occurred")
                # Maybe we could recover from this point, but
                # break is probably safer for avoid zombie connections
                break

        log.i("Connection closed with client %s", self._client)

        print(red(f"[{self._client.tag}] disconnected "
                  f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))

    def _recv(self):
        log.d("Waiting for messages from %s...", self._client)
        req_payload_data = self._client.stream.read()

        # Parse the request to JSON
        req_payload = None

        try:
            req_payload = btoj(req_payload_data)
        except:
            log.exception("Failed to parse payload - discarding it")

        # Handle the request (if it's valid) and take out the response

        if is_request(req_payload):
            # Trace IN
            if is_tracing_enabled():  # check for avoid json_pretty_str call
                trace_in(f"{j(req_payload)}",
                         ip=self._client.endpoint[0],
                         port=self._client.endpoint[1])

            try:
                resp_payload = self._handle_request(req_payload)
            except:
                log.exception("Exception occurred while handling request")
                resp_payload = create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)
        else:
            log.e("Invalid request - discarding it: %s", req_payload)
            resp_payload = create_error_response(ServerErrors.INVALID_REQUEST)

        # Send the response
        self._send_response(resp_payload)


    def _handle_request(self, request: Request) -> Response:
        api = request.get("api")
        if not api:
            return create_error_response(ServerErrors.INVALID_REQUEST)

        if api not in self._request_dispatcher:
            return create_error_response(ServerErrors.UNKNOWN_API)

        return self._request_dispatcher[api](request.get("params", {}))

    def _send_response(self, response: Response):
        if not response:
            log.d("null response, sending nothing")
            return

        # Trace OUT
        if is_tracing_enabled(): # check for avoid json_pretty_str call
            trace_out(f"{j(response)}",
                     ip=self._client.endpoint[0],
                     port=self._client.endpoint[1])

        # Really send it back
        self._client.stream.write(jtob(response))

    def _sleep(self, params: RequestParams) -> Response:
        log.d("Sleeping...")
        time.sleep(int(params.get("time", 1)))
        log.d("Slept")
        return create_success_response()


    def _connect(self, params: RequestParams) -> Response:
        log.i("<< CONNECT  |  %s", self._client)

        password = params.get("password")

        if self._connected:
            log.w("Client already connected")
            return create_success_response()

        # Authentication
        log.i("Authentication check - type: %s", self._api_service.auth().algo_type())

        # Just ask the auth whether it matches or not
        # (The password can either be none/plain/hash, the auth handles them all)
        if not self._api_service.auth().authenticate(password):
            log.e("Authentication FAILED")
            return create_error_response(ServerErrors.AUTHENTICATION_FAILED)
        else:
            log.i("Authentication OK")

        self._connected = True

        print(green(f"[{self._client.tag}] connected "
                    f"({self._client.endpoint[0]}:{self._client.endpoint[1]})"))

        return create_success_response()


    def _disconnect(self, _: RequestParams):
        log.i("<< DISCONNECT  |  %s", self._client)

        if not self._connected:
            log.w("Already disconnected")

        self._connected = False

        return create_success_response()


    def _list(self, _: RequestParams):
        log.i("<< LIST  |  %s", self._client)

        return create_success_response([sh.info() for sh in self._api_service.sharings()])


    def _info(self, _: RequestParams):
        log.i("<< INFO  |  %s", self._client)

        return create_success_response(
            self._api_service.server_info()
        )


    def _ping(self, _: RequestParams):
        log.i("<< PING  |  %s", self._client)

        return create_success_response("pong")

    @ensure_connected
    @ensure_unix
    @ensure_rexec_enabled
    def _rexec(self, params: RequestParams):
        cmd = params.get("cmd")
        if not cmd:
            create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< REXEC %s |  %s", cmd, self._client)


        self._send_response(create_success_response())

        rexec_service = RexecService(self._client, cmd)
        retcode = rexec_service.run()

        log.d("Rexec finished")

        return create_success_response(retcode)

    # @expose
    # @trace_api
    # @require_connected_client
    # @try_or_command_failed_response
    # def open(self, sharing_name: str) -> Response:
    #     if not sharing_name:
    #         return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)
    #
    #     sharing: Sharing = self._sharings.get(sharing_name)
    #
    #     if not sharing:
    #         return create_error_response(ServerErrors.SHARING_NOT_FOUND, q(sharing_name))
    #
    #     client = self._current_request_client()
    #
    #     log.i("<< OPEN %s [%s]", sharing_name, client)
    #
    #     serving = SharingService(
    #         server_port=self._port,
    #         sharing=sharing,
    #         sharing_rcwd=sharing.path,
    #         client=client
    #     )
    #
    #     uid = serving.publish()
    #
    #     log.i("Opened sharing UID: %s", uid)
    #
    #     print(f"[{client.tag}] open '{sharing_name}'")
    #
    #     return create_success_response(uid)
    #
    #

    # @expose
    # @trace_api
    # @try_or_command_failed_response
    # def rexec(self, cmd: str) -> Response:
    #     if not self._rexec_enabled:
    #         log.w("Client attempted remote command execution; denying since rexec is disabled")
    #         return create_error_response(ServerErrors.NOT_ALLOWED)
    #
    #     # Check that we are on Unix
    #
    #     if not is_unix():
    #         log.w("rexec not supported on this platform")
    #         return create_error_response(ServerErrors.SUPPORTED_ONLY_FOR_UNIX)
    #
    #
    #     client = self._current_request_client()
    #     if not client:
    #         return create_error_response(ServerErrors.NOT_CONNECTED)
    #
    #     log.i(">> REXEC %s [%s]", cmd, client)
    #
    #     rx = RexecService(
    #         cmd,
    #         client=client
    #     )
    #     rx.run()
    #
    #     uri = rx.publish()
    #
    #     log.d("Rexec handler initialized; uri: %s", uri)
    #
    #     print(f"[{client.tag}] rexec '{cmd}'")
    #
    #     return create_success_response(uri)
    #
    # @expose
    # @trace_api
    # @try_or_command_failed_response
    # def rshell(self) -> Response:
    #     if not self._rexec_enabled:
    #         log.w("Client attempted remote command execution; denying since rexec is disabled")
    #         return create_error_response(ServerErrors.NOT_ALLOWED)
    #
    #     if not is_unix():
    #         log.w("rshell not supported on this platform")
    #         return create_error_response(ServerErrors.SUPPORTED_ONLY_FOR_UNIX)
    #
    #     client = self._current_request_client()
    #     if not client:
    #         return create_error_response(ServerErrors.NOT_CONNECTED)
    #
    #     log.i(">> RSHELL [%s]", client)
    #
    #     rsh = RshellService(client=client)
    #     rsh.run()
    #
    #     uri = rsh.publish()
    #
    #     log.d("Rexec handler initialized; uri: %s", uri)
    #
    #     print(f"[{client.tag}] rshell")
    #
    #     return create_success_response(uri)