import platform
from typing import Union, Optional, cast, List, Dict

from easyshare.common import TransferProtocol, TransferDirection, APP_VERSION
from easyshare.consts import ansi
from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.requests import Requests, create_request, RequestsParams
from easyshare.protocol.responses import Response, is_success_response, create_error_response, is_error_response, \
    ServerErrors, create_success_response
from easyshare.protocol.types import ServerInfoFull, ServerInfo, FileType
from easyshare.sockets import SocketTcp, SocketTcpOut
from easyshare.ssl import get_ssl_context, set_ssl_context
from easyshare.streams import TcpStream
from easyshare.tracing import trace_json
from easyshare.utils.inspection import stacktrace
from easyshare.utils.json import j, jtob, btoj
from easyshare.utils.ssl import create_client_ssl_context

log = get_logger(__name__)



def require_server_connection(api):
    """
    Decorator for require the real connection before invoke an API.
    Raises a NOT_CONNECTED if is_connected() is False.
    """
    def require_server_connection_wrapper(conn: 'ConnectionMinimal', *vargs, **kwargs) -> Response:
        log.d("require_server_connection check before invoking '%s'", api.__name__)
        if not conn.is_connected_to_server():
            log.w("require_server_connection: FAILED")
            log.w(stacktrace(color=ansi.FG_YELLOW))
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("require_connected_connection: OK - invoking '%s'", api.__name__)
        return api(conn, *vargs, **kwargs)

    return require_server_connection_wrapper



def require_sharing_connection(api):
    """
    Decorator for require the real connection before invoke an API.
    Raises a NOT_CONNECTED if is_connected() is False.
    """
    def require_sharing_connection_wrapper(conn: 'ConnectionMinimal', *vargs, **kwargs) -> Response:
        log.d("require_sharing_connection check before invoking '%s'", api.__name__)
        if not conn.is_connected_to_sharing():
            log.w("require_sharing_connection: FAILED")
            log.w(stacktrace(color=ansi.FG_YELLOW))
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("require_sharing_connection: OK - invoking '%s'", api.__name__)
        return api(conn, *vargs, **kwargs)

    return require_sharing_connection_wrapper


def handle_connection_response(api):
    """
    Decorator for handle the response and taking some standard actions.
    e.g. destroy the connection in case of a NOT_CONNECTED response.
    """

    def handle_connection_response_wrapper(conn: 'ConnectionMinimal', *vargs, **kwargs) -> Response:
        log.d("Invoking '%s' and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling '%s' response", api.__name__)
        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            log.e("Detected NOT_CONNECTED response, destroying connection")
            conn.destroy_connection()
        return resp

    return handle_connection_response_wrapper


# =============================================
# ============ SERVER CONNECTION =============
# =============================================

class ConnectionMinimal:
    def __init__(self,
                 server_ip: str, server_port: int, server_ssl: bool,
                 server_alias: str = None, socket: SocketTcp = None):
        # Might throw ConnectionRefusedError
        log.i("Initializing new ServerConnection %s:%d%s (SSL=%s)",
              server_ip, server_port, "(" + server_alias + ")" if server_alias else "",
              server_ssl)

        self._server_ip = server_ip
        self._server_port = server_port
        self._server_ssl = server_ssl

        self._connected_to_server: bool = False
        self._connected_to_sharing: bool = False
        self._sharing_name: Optional[str] = None
        self._rcwd: Optional[str] = None

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
            self._stream = TcpStream(socket)
        else:
            self._stream = TcpStream(SocketTcpOut(
                address=server_ip,
                port=server_port,
                ssl_context=get_ssl_context()
            ))


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


    def is_established(self) -> bool:
        return True if self._stream else False

    def is_connected_to_server(self) -> bool:
        return True if self._connected_to_server and self._stream else False

    def is_connected_to_sharing(self) -> bool:
        return True if self.is_connected_to_server() and self._connected_to_sharing else False

    def current_sharing_name(self) -> Optional[str]:
        """ Current remote sharing name """
        return self._sharing_name if self.is_connected_to_sharing() else None

    def current_rcwd(self) -> Optional[str]:
        """ Current remote working directory (cached) """
        return self._rcwd if self.is_connected_to_sharing() else None

    def destroy_connection(self, clean: bool=True):
        log.d(f"Destroying connection, clean={clean}")

        if clean:
            # Clean means to send CLOSE and DISCONNECT as expected
            self.destroy_sharing_connection()
            self.destroy_server_connection()
        # else: just shutdown the socket, although the server won't be happy

        self._destroy_stream()


    def destroy_server_connection(self) -> Optional[Response]:
        log.d("Destroying server connection")
        resp = None
        if self._connected_to_server:
            try:
                log.d("Really sending disconnect()")
                resp = self.call(create_request(Requests.DISCONNECT))
            except:
                log.w("Failed to close sharing connection gracefully, "
                      "invaliding it anyway")

        self._connected_to_server = False
        return resp


    def destroy_sharing_connection(self) -> Optional[Response]:
        log.d("Destroying sharing connection")
        resp = None
        if self._connected_to_sharing:
            try:
                log.d("Really sending close()")
                resp = self.call(create_request(Requests.CLOSE))
            except:
                log.w("Failed to close sharing connection gracefully, "
                      "invaliding it anyway")

        self._connected_to_sharing = False
        self._sharing_name = None
        self._rcwd = None
        return resp

    def _destroy_stream(self):
        if self._stream:
            try:
                log.d("Closing underlying socket")
                self._stream.close()
            except:
                log.w("Failed to close socket gracefully")
            self._stream = None


    # === CONNECTION ESTABLISHMENT ===


    def connect(self, passwd) -> Response:
        # Compute user agent, not really used but is still an useful
        # information for debug what's happening
        useragent = f"es: {APP_VERSION} - "\
                    f"OS: {platform.system()} {platform.release()} - "\
                    f"Python: {platform.python_version()}"

        resp = self.call(create_request(Requests.CONNECT, {
            RequestsParams.CONNECT_PASSWORD: passwd,
            RequestsParams.CONNECT_USER_AGENT: useragent
        }))

        self._connected_to_server = is_success_response(resp)

        return resp

    @require_server_connection
    def disconnect(self) -> Response:
        resp = self.destroy_server_connection()
        self.destroy_connection() # close the underlying socket too
        return resp

    # === SERVER INFO RETRIEVAL ===


    @handle_connection_response
    def info(self) -> Response:
        return self.call(create_request(Requests.INFO))

    @handle_connection_response
    def list(self) -> Response:
        return self.call(create_request(Requests.LIST))

    @handle_connection_response
    def ping(self) -> Response:
        return self.call(create_request(Requests.PING))


    # === REAL SERVER FUNCS ===


    @handle_connection_response
    @require_server_connection
    def open(self, sharing_name) -> Response:
        resp = self.call(create_request(Requests.OPEN, {
            RequestsParams.OPEN_SHARING: sharing_name
        }))

        if is_success_response(resp):
            self._connected_to_sharing = True
            self._sharing_name = sharing_name
            self._rcwd = "/"
        # else?

        return resp

    @handle_connection_response
    @require_server_connection
    def rshell(self, cmd: str, cols: int, rows: int) -> Response:
        return self.call(create_request(Requests.RSHELL, {
            RequestsParams.RSHELL_CMD: cmd,
            RequestsParams.RSHELL_COLS: cols,
            RequestsParams.RSHELL_ROWS: rows
        }))

    # === REAL SHARING FUNCS ===


    @require_sharing_connection
    def close(self):
        return self.destroy_sharing_connection()    # leave the socket open
                                                    # (for server connection)

    @require_sharing_connection
    def rpwd(self) -> Response:
        return create_success_response(self._rcwd)  # cached

    @handle_connection_response
    @require_sharing_connection
    def rcd(self, path) -> Response:
        resp = self.call(create_request(Requests.RCD, {
            RequestsParams.RCD_PATH: path
        }))

        if is_success_response(resp):
            self._rcwd = resp["data"]

        return resp

    @handle_connection_response
    @require_sharing_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False, details: bool = False, path: str = None) -> Response:
        return self.call(create_request(Requests.RLS, {
            RequestsParams.RLS_PATH: path,
            RequestsParams.RLS_SORT_BY: sort_by,
            RequestsParams.RLS_REVERSE: reverse,
            RequestsParams.RLS_HIDDEN: hidden,
            RequestsParams.RLS_DETAILS: details
        }))

    @handle_connection_response
    @require_sharing_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, details: bool = False, path: str = None) -> Response:
        return self.call(create_request(Requests.RTREE, {
            RequestsParams.RTREE_PATH: path,
            RequestsParams.RTREE_SORT_BY: sort_by,
            RequestsParams.RTREE_REVERSE: reverse,
            RequestsParams.RTREE_HIDDEN: hidden,
            RequestsParams.RTREE_DEPTH: max_depth,
            RequestsParams.RTREE_DETAILS: details
        }))

    @handle_connection_response
    @require_sharing_connection
    def rfind(self, name: str = None, regex: str = None, case_sensitive: bool = True,
              ftype: FileType = None, details: bool = False, path: str = None) -> Response:

        return self.call(create_request(Requests.RFIND, {
            RequestsParams.RFIND_PATH: path,
            RequestsParams.RFIND_NAME: name,
            RequestsParams.RFIND_REGEX: regex,
            RequestsParams.RFIND_CASE_SENSITIVE: case_sensitive,
            RequestsParams.RFIND_FTYPE: ftype,
            RequestsParams.RFIND_DETAILS: details,
        }))

    @handle_connection_response
    @require_sharing_connection
    def rdu(self, path: str = None) -> Response:

        return self.call(create_request(Requests.RDU, {
            RequestsParams.RDU_PATH: path,
        }))

    @handle_connection_response
    @require_sharing_connection
    def rmkdir(self, directory) -> Response:
        return self.call(create_request(Requests.RMKDIR, {
            RequestsParams.RMKDIR_PATH: directory
        }))

    @handle_connection_response
    @require_sharing_connection
    def rrm(self, paths: List[str]) -> Response:
        return self.call(create_request(Requests.RRM, {
            RequestsParams.RRM_PATHS: paths
        }))

    @handle_connection_response
    @require_sharing_connection
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self.call(create_request(Requests.RMV, {
            RequestsParams.RMV_SOURCES: sources,
            RequestsParams.RMV_DESTINATION: destination
        }))

    @handle_connection_response
    @require_sharing_connection
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self.call(create_request(Requests.RCP, {
            RequestsParams.RCP_SOURCES: sources,
            RequestsParams.RCP_DESTINATION: destination
        }))

    @handle_connection_response
    @require_sharing_connection
    def get(self,
            paths: List[str],
            check: bool,
            no_hidden: bool = False,
            mmap: Optional[bool] = None,
            chunk_size: Optional[int] = None) -> Response:

        req_params = {
            RequestsParams.GET_PATHS: paths,
            RequestsParams.GET_CHECK: check,
            RequestsParams.GET_NO_HIDDEN: no_hidden,
        }


        # Secret params
        if mmap is not None:
            req_params[RequestsParams.GET_MMAP] = mmap
        if chunk_size is not None:
            req_params[RequestsParams.GET_CHUNK_SIZE] = chunk_size

        return self.call(create_request(Requests.GET, req_params))

    @handle_connection_response
    @require_sharing_connection
    def put(self, check: bool, sync: bool, preview: bool) -> Response:
        return self.call(create_request(Requests.PUT, {
            RequestsParams.PUT_CHECK: check,
            RequestsParams.PUT_SYNC: sync,
            RequestsParams.PUT_PREVIEW: preview,
        }))


    # === INTERNALS ===


    def call(self, req: Dict) -> Response:
        self.write_json(req)
        return self.read_json()

    def write_json(self, req: Dict):
        trace_json(req,
                   sender=self._stream.endpoint(), receiver=self._stream.remote_endpoint(),
                   direction=TransferDirection.OUT, protocol=TransferProtocol.TCP)

        self.write(jtob(req), trace=False)

    def read_json(self) -> Dict:
        resp = btoj(self.read(trace=False))

        trace_json(
            resp,
            sender=self._stream.remote_endpoint(), receiver=self._stream.endpoint(),
            direction=TransferDirection.IN, protocol=TransferProtocol.TCP
        )

        return resp


    def write(self, data: Union[bytes, bytearray], trace: bool = True):
        if not self.is_established():
            raise ConnectionError("Connection closed")

        try:
            self._stream.write(data, trace=trace)
        except KeyboardInterrupt as kex:
            # Pass the KeyboardInterrupt above, so that it could be handled
            # it in a different manner than just shutdown the connection
            log.w("CTRL+C while writing to socket, "
                  "it will be probably remain in an inconsistent state")
            raise kex
        except:
            self._destroy_stream()
            raise ConnectionError("Write failed")


    def read(self, trace: bool = True) -> bytearray:
        if not self.is_established():
            raise ConnectionError("Connection closed")

        try:
            return self._stream.read(trace=trace)
        except KeyboardInterrupt as kex:
            # Pass the KeyboardInterrupt above, so that it could be handled
            # it in a different manner than just shutdown the connection
            log.w("CTRL+C while reading from socket, "
                  "it will be probably remain in an inconsistent state")
            raise kex
        except:
            self._destroy_stream()
            raise ConnectionError("Write failed")


class Connection(ConnectionMinimal):
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
