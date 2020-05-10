import ssl
from typing import Union, Optional, cast, List

from easyshare.common import ESD_PYRO_UID
from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol import ServerErrors, SharingInfo, ISharingService, create_success_response
from easyshare.protocol import IServer
from easyshare.protocol import Response, is_success_response, create_error_response, is_error_response
from easyshare.protocol import ServerInfoFull, ServerInfo
from easyshare.ssl import get_ssl_context, set_ssl_context
from easyshare.utils.json import j
from easyshare.utils.pyro.client import TracedPyroProxy
from easyshare.utils.pyro.common import pyro_uri
from easyshare.utils.ssl import create_client_ssl_context


log = get_logger(__name__)


# =============================================
# ============ SERVER CONNECTION =============
# =============================================


def require_server_connection(api):
    def require_server_connection_api_wrapper(conn: 'ServerConnection', *vargs, **kwargs) -> Response:
        log.d("Checking esd connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("@require_server_connection : invalid connection")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)

    require_server_connection_api_wrapper.__name__ = api.__name__

    return require_server_connection_api_wrapper


def handle_server_response(api):
    def handle_server_response_api_wrapper(conn: 'ServerConnection', *vargs, **kwargs) -> Response:
        log.d("Invoking '%s' and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling '%s' response", api.__name__)
        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            log.e("Detected NOT_CONNECTED response, destroying connection")
            conn._destroy_connection()
        return resp

    handle_server_response_api_wrapper.__name__ = __name__

    return handle_server_response_api_wrapper


class ServerConnectionMinimal:

    def __init__(self,
                 server_ip: str, server_port: int, server_ssl: bool, server_alias: str = None,
                 established_server_connection: Union[IServer, TracedPyroProxy] = None):
        log.i("Initializing new ServerConnection %s:%d%s (SSL=%s)",
              server_ip, server_port, "(" + server_alias + ")" if server_alias else "",
              server_ssl
              )

        self._connected = False
        self._server_ip = server_ip
        self._server_port = server_port
        self._server_ssl = server_ssl

        # self.server_info: ServerInfoFull = server_info

        # Create the proxy for the remote esd
        if established_server_connection:
            log.d("Not creating connection since an established one as been provided")
            self.server = established_server_connection
        else:
            self.server: Union[IServer, TracedPyroProxy] = TracedPyroProxy(
                pyro_uri(ESD_PYRO_UID, server_ip, server_port),
                alias=server_alias
            )

        if server_ssl:
            if not get_ssl_context():
                # This is actually not really clean, since we are overwriting
                # the global ssl_context of Pyro, but potentially we could have
                # a 'Connection' to a SSL esd and a 'Connection' to a non SSL esd.
                # In practice this never happens because the es is implemented
                # as an interactive shell, thus supports just one connection at a time
                set_ssl_context(create_client_ssl_context())
        else:
            # Destroy any previous ssl context
            set_ssl_context(None)

    def is_connected(self) -> bool:
        return self._connected is True and self.server

    def ssl_certificate(self) -> Optional[bytes]:
        return self.server._pyroConnection.sock.getpeercert(binary_form=True) if \
            isinstance(self.server._pyroConnection.sock, ssl.SSLSocket) else None

    def server_ip(self) -> str:
        return self._server_ip

    def server_port(self) -> int:
        return self._server_port

    def server_ssl(self) -> bool:
        return self._server_ssl

    @handle_server_response
    # NO @require_server_connection
    def connect(self, password: str = None) -> Response:
        resp = self.server.connect(password=password)

        self._connected = is_success_response(resp)

        return resp

    # NO @handle_server_response
    @require_server_connection
    def disconnect(self) -> Response:
        resp = self.server.disconnect()

        self._destroy_connection()

        return resp

    @handle_server_response
    @require_server_connection
    def open(self, sharing_name) -> Response:
        return self.server.open(sharing_name)

    @handle_server_response
    # @require_server_connection
    def info(self) -> Response:
        return self.server.info()

    @handle_server_response
    # @require_server_connection
    def list(self) -> Response:
        return self.server.list()

    @handle_server_response
    # @require_server_connection
    def ping(self) -> Response:
        return self.server.ping()

    @handle_server_response
    @require_server_connection
    def rexec(self, cmd: str) -> Response:
        return self.server.rexec(cmd)

    def _destroy_connection(self):
        log.d("Marking esd connection as disconnected")
        self._connected = False

        if self.server:
            log.d("Releasing pyro resources of the esd connection")
            self.server._pyroRelease()
            self.server = None
        else:
            log.w("Server connection already invalid, nothing to release")


class ServerConnection(ServerConnectionMinimal):

    def __init__(self,
                 server_ip: str, server_port: int,
                 server_info: ServerInfo,
                 established_server_connection: Union[IServer, TracedPyroProxy] = None):
        super().__init__(
            server_ip=server_ip,
            server_port=server_port,
            server_ssl=server_info.get("ssl"),
            server_alias=server_info.get("name"),
            established_server_connection=established_server_connection
        )

        self.server_info: ServerInfoFull = cast(ServerInfoFull, server_info)
        self.server_info["ip"] = server_ip
        self.server_info["port"] = server_port

        log.d("Server connection info: \n%s", j(self.server_info))



# =============================================
# ============ SHARING CONNECTION =============
# =============================================



def require_sharing_connection(api):
    def require_sharing_connection_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Checking sharing connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("@require_sharing_connection : invalid connection")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Sharing connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)

    require_sharing_connection_api_wrapper.__name__ = api.__name__

    return require_sharing_connection_api_wrapper


def handle_sharing_response(api):
    def handle_sharing_response_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Invoking %s and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling %s response", api.__name__)

        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            conn._destroy_connection()

        return resp

    handle_sharing_response_api_wrapper.__name__ = __name__

    return handle_sharing_response_api_wrapper


class SharingConnection:

    def __init__(self, sharing_uid: str,
                 sharing_info: SharingInfo,
                 server_info: ServerInfoFull):
        log.i("Initializing new SharingConnection")
        log.d("Bound to server info:\n%s", j(server_info))

        self.sharing_info = sharing_info
        self.server_info = server_info

        self._connected = True  # Start as connected,
                                # we already have opened the remote serving
        self._rcwd = ""

        # Create the proxy for the remote sharing
        self.service: Union[ISharingService, TracedPyroProxy] = TracedPyroProxy(
            pyro_uri(sharing_uid, server_info.get("ip"), server_info.get("port")),
            alias="{}{}{}".format(
                sharing_info.get("name") if sharing_info else "",
                "@" if sharing_info and server_info else "",
                server_info.get("name") if server_info else ""
            )
        )

    def is_connected(self) -> bool:
        return self._connected is True and self.service

    def rcwd(self) -> str:
        return self._rcwd

    # =====

    # NO @handle_response (async)
    @require_sharing_connection
    def close(self):
        self.service.close()         # async
        self._destroy_connection()


    @require_sharing_connection
    def rpwd(self) -> Response:
        return create_success_response(self._rcwd)  # cached

    @handle_sharing_response
    @require_sharing_connection
    def rcd(self, path) -> Response:
        resp = self.service.rcd(path)

        if is_success_response(resp):
            self._rcwd = resp["data"]

        return resp

    @handle_sharing_response
    @require_sharing_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False,  path: str = None) -> Response:
        return self.service.rls(path=path, sort_by=sort_by,
                                reverse=reverse, hidden=hidden)

    @handle_sharing_response
    @require_sharing_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, path: str = None) -> Response:
        return self.service.rtree(path=path, sort_by=sort_by, reverse=reverse,
                                  hidden=hidden, max_depth=max_depth)

    @handle_sharing_response
    @require_sharing_connection
    def rmkdir(self, directory) -> Response:
        return self.service.rmkdir(directory)

    @handle_sharing_response
    @require_sharing_connection
    def rrm(self, paths: List[str]) -> Response:
        return self.service.rrm(paths)

    @handle_sharing_response
    @require_sharing_connection
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self.service.rmv(sources, destination)

    @handle_sharing_response
    @require_sharing_connection
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self.service.rcp(sources, destination)

    @handle_sharing_response
    @require_sharing_connection
    def get(self, files: List[str], check: bool) -> Response:
        return self.service.get(files, check)

    @handle_sharing_response
    @require_sharing_connection
    def put(self, check: bool) -> Response:
        return self.service.put(check)

    def _destroy_connection(self):
        log.d("Marking sharing connection as disconnected")
        self._connected = False

        if self.service:
            log.d("Releasing pyro resources of the sharing connection")
            self.service._pyroRelease()
            self.service = None
        else:
            log.w("Sharing connection already invalid, nothing to release")

