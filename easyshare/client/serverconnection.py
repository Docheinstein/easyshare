import ssl
from typing import Union, Optional

from easyshare.client.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.exposed import IServer
from easyshare.protocol.response import Response, is_success_response, create_error_response, is_error_response
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.common import esd_pyro_uri
from easyshare.ssl import get_ssl_context, set_ssl_context
from easyshare.utils.pyro import TracedPyroProxy
from easyshare.utils.ssl import create_client_ssl_context


log = get_logger(__name__)


def require_server_connection(api):
    def require_server_connection_api_wrapper(conn: 'ServerConnection', *vargs, **kwargs) -> Response:
        log.d("Checking server connection validity before invoking %s", api.__name__)
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
            conn._destroy_connection()
        return resp

    handle_server_response_api_wrapper.__name__ = __name__

    return handle_server_response_api_wrapper


class ServerConnection:

    def __init__(self,
                 server_info: ServerInfo,
                 established_server_connection: Union[IServer, TracedPyroProxy] = None):
        log.d("Initializing new ServerConnection")
        self._connected = False

        self.server_info: ServerInfo = server_info

        # Create the proxy for the remote server
        if established_server_connection:
            log.d("Not creating connection since an established one as been provided")
            self.server = established_server_connection
        else:
            self.server: Union[IServer, TracedPyroProxy] = TracedPyroProxy(
                esd_pyro_uri(server_info.get("ip"), server_info.get("port")),
                alias=server_info.get("name")
            )

        if server_info.get("ssl"):
            if not get_ssl_context():
                # This is actually not really clean, since we are overwriting
                # the global ssl_context of Pyro, but potentially we could have
                # a 'Connection' to a SSL server and a 'Connection' to a non SSL server.
                # In practice this never happens because the client is implemented
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
        log.d("Marking server connection as disconnected")
        self._connected = False

        if self.server:
            log.d("Releasing pyro resources of the server connection")
            self.server._pyroRelease()
            self.server = None
        else:
            log.w("Server connection already invalid, nothing to release")
