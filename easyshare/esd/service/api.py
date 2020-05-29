import threading
from typing import List, Dict

from easyshare.auth import Auth
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, Client
from easyshare.esd.daemons.api import get_api_daemon
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfo
from easyshare.sockets import SocketTcp
from easyshare.ssl import get_ssl_context
from easyshare.utils.json import bytes_to_json, j
from easyshare.utils.types import bytes_to_int

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

    def handle(self):
        log.i("Handling client %s", self._client)

        while True:
            self._recv()


    def _recv(self):
        log.d("Waiting for messages from %s...", self._client)
        header_data = self._client.socket.recv(2)
        header = bytes_to_int(header_data)

        payload_size = header

        log.d("Received an header, payload will be: %d bytes", payload_size)

        payload_data = self._client.socket.sock.recv(payload_size)
        payload = bytes_to_json(payload_data)

        log.d("Received payload \n%s", j(payload))

