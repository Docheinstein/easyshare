from typing import Union, Optional, cast


from easyshare.es.connections import Connection
from easyshare.logging import get_logger
from easyshare.protocol.requests import Request
from easyshare.protocol.responses import Response
from easyshare.protocol.stream import Stream
from easyshare.protocol.types import ServerInfoFull, ServerInfo
from easyshare.sockets import SocketTcp, SocketTcpOut
from easyshare.ssl import get_ssl_context, set_ssl_context
from easyshare.utils.json import j, jtob, btoj
from easyshare.utils.ssl import create_client_ssl_context

log = get_logger(__name__)


# =============================================
# ============ SERVER CONNECTION =============
# =============================================

class ServerConnectionMinimal(Connection):
    def __init__(self,
                 server_ip: str, server_port: int, server_ssl: bool,
                 server_alias: str = None, socket: SocketTcp = None):
        # Might throw ConnectionRefusedError
        log.i("Initializing new ServerConnection %s:%d%s (SSL=%s)",
              server_ip, server_port, "(" + server_alias + ")" if server_alias else "",
              server_ssl)

        self._connected = False
        self._server_ip = server_ip
        self._server_port = server_port
        self._server_ssl = server_ssl

        # SSL setting

        if server_ssl:
            if not get_ssl_context():
                set_ssl_context(create_client_ssl_context())
        else:
            # Destroy any previous ssl context
            set_ssl_context(None)

        # Connect to the remote
        if socket:
            log.d("Not creating connection since an established one as been provided")
            self._stream = Stream(socket)
        else:
            self._stream = Stream(SocketTcpOut(
                address=server_ip,
                port=server_port,
                ssl_context=get_ssl_context()
            ))

    def is_established(self) -> bool:
        return True if self._stream else False

    def destroy(self):
        log.d("Destroying connection")
        if self._stream:
            try:
                self._stream.close()
            except:
                log.w("Socket close failed")
            self._stream = None

    def call(self, request: Request) -> Response:
        self.write(jtob(request))
        return btoj(self.read())

    def write(self, data: Union[bytes, bytearray]):
        if not self.is_established():
            raise ConnectionError("Connection closed")

        try:
            self._stream.write(data)
        except:
            log.e("Write failed - destroying connection")
            self.destroy()
            raise ConnectionError("Write failed")


    def read(self) -> bytearray:
        if not self.is_established():
            raise ConnectionError("Connection closed")

        try:
            return self._stream.read()
        except:
            log.e("Read failed - destroying connection")
            self.destroy()
            raise ConnectionError("Write failed")

    def ssl_certificate(self) -> Optional[bytes]:
        """
        Returns the SSL certificate of this connection in binary form,
        or None if SSL is disabled
        """
        return self._stream._socket.ssl_certificate()

    def server_ip(self) -> str:
        """ IP of the remote server """
        return self._server_ip

    def server_port(self) -> int:
        """ Port of the remote server """
        return self._server_port

    def server_ssl(self) -> bool:
        """ Whether SSL is enabled for this connection """
        return self._server_ssl


#
# class ServerConnectionMinimal(Connection):
#     """
#     Minimal server connection to a remote 'Server'.
#     The difference with 'ServerConnection' is that he latter offers more information
#     about the server (a 'ServerInfo'), which could have been retrieved after
#     the connection establishment.
#     Basically its a wrapper around the exposed method of 'IServer',
#     but adds tracing.
#     """
#
#     def __init__(self,
#                  server_ip: str, server_port: int, server_ssl: bool, server_alias: str = None,
#                  established_server_connection: Union[IServer, TracedPyroProxy] = None):
#         log.i("Initializing new ServerConnection %s:%d%s (SSL=%s)",
#               server_ip, server_port, "(" + server_alias + ")" if server_alias else "",
#               server_ssl)
#
#         self._connected = False
#         self._server_ip = server_ip
#         self._server_port = server_port
#         self._server_ssl = server_ssl
#
#         # Create the proxy for the remote server
#         if established_server_connection:
#             log.d("Not creating connection since an established one as been provided")
#             self.server = established_server_connection
#         else:
#             self.server: Union[IServer, TracedPyroProxy] = TracedPyroProxy(
#                 pyro_uri(ESD_PYRO_UID, server_ip, server_port),
#                 alias=server_alias
#             )
#
#         if server_ssl:
#             if not get_ssl_context():
#                 # This is actually not really clean, since we are overwriting
#                 # the global ssl_context of Pyro, but potentially we could have
#                 # a 'Connection' to a SSL server and a 'Connection' to a non SSL server.
#                 # In practice this never happens because the client is implemented
#                 # as an interactive shell, thus supports just one connection at a time
#                 set_ssl_context(create_client_ssl_context())
#         else:
#             # Destroy any previous ssl context
#             set_ssl_context(None)
#
#     def is_connected(self) -> bool:
#         return self._connected is True and self.server
#
#     def destroy_connection(self):
#         log.d("Marking server connection as disconnected")
#         self._connected = False
#
#         if self.server:
#             log.d("Releasing pyro resources of the server connection")
#             self.server._pyroRelease()
#             self.server = None
#         else:
#             log.w("Server connection already invalid, nothing to release")
#
#     def ssl_certificate(self) -> Optional[bytes]:
#         """
#         Returns the SSL certificate of this connection in binary form,
#         or None if SSL is disabled
#         """
#         if isinstance(self.server._pyroConnection.sock, ssl.SSLSocket):
#             return self.server._pyroConnection.sock.getpeercert(binary_form=True)
#         return None
#
#     def server_ip(self) -> str:
#         """ IP of the remote server """
#         return self._server_ip
#
#     def server_port(self) -> int:
#         """ Port of the remote server """
#         return self._server_port
#
#     def server_ssl(self) -> bool:
#         """ Whether SSL is enabled for this connection """
#         return self._server_ssl
#
#
#     # === CONNECTION ESTABLISHMENT ===
#
#
#     @handle_connection_response
#     # NO @require_server_connection
#     def connect(self, password: str = None) -> Response:
#         resp = self.server.connect(password=password)
#
#         self._connected = is_success_response(resp)
#
#         return resp
#
#     @require_connected_connection
#     def disconnect(self) -> Response:
#         resp = self.server.disconnect()
#
#         self.destroy_connection()
#
#         return resp
#
#
#     # === SERVER INFO RETRIEVAL ===
#
#
#     @handle_connection_response
#     def info(self) -> Response:
#         return self.server.info()
#
#     @handle_connection_response
#     def list(self) -> Response:
#         return self.server.list()
#
#     @handle_connection_response
#     def ping(self) -> Response:
#         return self.server.ping()
#
#
#     # === REAL ACTIONS ===
#
#
#     @handle_connection_response
#     @require_connected_connection
#     def open(self, sharing_name) -> Response:
#         return self.server.open(sharing_name)
#
#     @handle_connection_response
#     @require_connected_connection
#     def rexec(self, cmd: str) -> Response:
#         return self.server.rexec(cmd)
#
#     @handle_connection_response
#     @require_connected_connection
#     def rshell(self) -> Response:
#         return self.server.rshell()
#

class ServerConnection(ServerConnectionMinimal):
    """
    Complete server connection; in addition to 'ServerConnectionMinimal' provide
    a 'ServerInfo', which contains more information compared to the bare name/ip/addr
    of the server provided by 'ServerConnectionMinimal'.
    The idea is tha 'ServerConnectionMinimal' is created for made the connection,
    but than an info should be retrieved (via info, or if already got with a discover)
    and the connection should be upgraded to a 'ServerConnection' for further uses.
    """

    def __init__(self,
                 server_ip: str, server_port: int,
                 server_info: ServerInfo,
                 socket: SocketTcp = None):
        super().__init__(
            server_ip=server_ip,
            server_port=server_port,
            server_ssl=server_info.get("ssl"),
            server_alias=server_info.get("name"),
            socket=socket
        )

        self.server_info: ServerInfoFull = cast(ServerInfoFull, server_info)
        self.server_info["ip"] = server_ip
        self.server_info["port"] = server_port

        log.d("Server connection info: \n%s", j(self.server_info))
