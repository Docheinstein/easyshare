from typing import List, Dict

from easyshare.auth import Auth
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing, ClientContext
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfo
from easyshare.sockets import SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


class ServerService:
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

        self._clients: Dict[Endpoint, ClientContext] = {}

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

    def _handle_new_connection(self, sock: SocketTcpIn) -> bool:
        log.i("Received new client connection from %s", sock)

        return True  # handled


    def _add_client(self, sock):
        pass
