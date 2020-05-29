import threading
from json import JSONDecodeError
from pathlib import Path
from typing import List, Dict, Callable

from easyshare.auth import Auth
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, Client
from easyshare.esd.daemons.api import get_api_daemon
from easyshare.logging import get_logger
from easyshare.protocol.requests import Request, is_request, Requests, RequestParams
from easyshare.protocol.responses import create_error_response, ServerErrors, Response, create_success_response
from easyshare.protocol.stream import Stream, StreamClosedError
from easyshare.protocol.types import ServerInfo
from easyshare.sockets import SocketTcp
from easyshare.ssl import get_ssl_context
from easyshare.utils.json import bytes_to_json, j, json_to_bytes
from easyshare.utils.os import ls
from easyshare.utils.types import bytes_to_int, int_to_bytes

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
        client = Client(client_sock)
        client_handler = ClientHandler(client)
        log.i("Adding client %s", client)
        with self._clients_lock:
            self._clients[client.endpoint] = client_handler
        client_handler.handle()


        pass


class ClientHandler:

    def __init__(self, client: Client):
        self._client = client
        self._client_stream = Stream(self._client.socket)

        self._request_dispatcher: Dict[str, Callable[[RequestParams], Response]] = {
            Requests.LS: self._ls
        }

    def handle(self):
        log.i("Handling client %s", self._client)

        while self._client_stream.is_open():
            try:
                self._recv()
            except StreamClosedError:
                pass
            except:
                log.exception("Unexpected exception occurred")

        log.i("Connection closed with client %s", self._client)

    def _recv(self):
        log.d("Waiting for messages from %s...", self._client)
        req_payload_data = self._client_stream.read()

        # Parse the request to JSON
        req_payload = None

        try:
            req_payload = bytes_to_json(req_payload_data)
        except:
            log.exception("Failed to parse payload - discarding it")

        # Handle the request (if it's valid) and take out the response

        if is_request(req_payload):
            try:
                resp_payload = self._handle_request(req_payload)
            except:
                log.exception("Exception occurred while handling request")
                resp_payload = create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)
        else:
            log.e("Invalid request - discarding it: %s", req_payload)
            resp_payload = create_error_response(ServerErrors.INVALID_REQUEST)

        if not resp_payload:
            resp_payload = create_error_response(ServerErrors.INTERNAL_SERVER_ERROR)

        # Send the response
        self._client_stream.write(json_to_bytes(resp_payload))


    def _handle_request(self, request: Request) -> Response:
        api = request.get("api")
        if not api:
            return create_error_response(ServerErrors.INVALID_REQUEST)

        if api not in self._request_dispatcher:
            return create_error_response(ServerErrors.UNKNOWN_API)

        return self._request_dispatcher[api](request.get("params"))


    def _ls(self, params: RequestParams) -> Response:
        return create_success_response(ls(Path()))
