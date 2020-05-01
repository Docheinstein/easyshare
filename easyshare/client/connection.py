import ssl
from typing import List, Union, Optional

import Pyro4

from easyshare.client.errors import ClientErrors
from easyshare.client.server import ServerProxy
from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.response import Response, create_error_response, is_success_response, is_data_response, \
    is_error_response
from easyshare.protocol.pyro import IServer
from easyshare.protocol.serverinfo import ServerInfo


log = get_logger(__name__)


def require_connection(api):
    def require_connection_api_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("Checking connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("@require_connection : invalid connection")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)
    return require_connection_api_wrapper


def handle_response(api):
    def handle_response_api_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("Invoking %s and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling %s response", api.__name__)
        conn._handle_response(resp)
        return resp

    return handle_response_api_wrapper


class Connection:

    def __init__(self, server_info: ServerInfo):
        log.d("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self._connected = False
        self._sharing_name = None
        self._rpwd = ""

        # Create the proxy for the remote server
        self.server: Union[IServer, ServerProxy] = ServerProxy(server_info)
        # Pyro4.asyncproxy(self.server)

    def is_connected(self) -> bool:
        return self._connected is True and self.server

    def sharing_name(self) -> str:
        return self._sharing_name

    def ssl_certificate(self) -> Optional[bytes]:
        return self.server._pyroConnection.sock.getpeercert(binary_form=True) if \
            isinstance(self.server._pyroConnection.sock, ssl.SSLSocket) else None

    # =====

    @handle_response
    # NO @require_connection (open() will establish it)
    def open(self, sharing_name: str, password: str = None) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.open(sharing_name, password)

        # resp = resp_future.value
        resp = resp_future

        if is_success_response(resp):
            self._connected = True
            self._sharing_name = sharing_name

        return resp

    # NO @handle_response (async)
    @require_connection
    def close(self):
        self.server.close()         # async
        self._destroy_connection()

    def rpwd(self) -> str:
        return self._rpwd

    @handle_response
    @require_connection
    def rcd(self, path) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rcd(path)

        resp = resp_future.value

        if is_success_response(resp):
            self._rpwd = resp["data"]

        return resp

    @handle_response
    @require_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False,  path: str = None) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rls(path=path, sort_by=sort_by,
                            reverse=reverse, hidden=hidden)
        return resp_future
        # return resp_future.value

    @handle_response
    @require_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, path: str = None) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rtree(path=path, sort_by=sort_by, reverse=reverse,
                              hidden=hidden, max_depth=max_depth)

        return resp_future.value

    @handle_response
    @require_connection
    def rmkdir(self, directory) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rmkdir(directory)

        return resp_future.value

    @handle_response
    @require_connection
    def rrm(self, paths: List[str]) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rrm(paths)

        return resp_future.value

    @handle_response
    @require_connection
    def rmv(self, sources: List[str], destination: str) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rmv(sources, destination)

        return resp_future.value

    @handle_response
    @require_connection
    def rcp(self, sources: List[str], destination: str) -> Response:
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rcp(sources, destination)

        return resp_future.value

    def ping(self) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.ping()

    # def rexec(self, cmd: str) -> Response:
    def rexec(self, cmd: str) -> Response:
        # if not self.is_connected():
        #     return create_error_response(ClientErrors.NOT_CONNECTED)

        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rexec(cmd)

        return resp_future

    def rexec_recv(self, transaction: str) -> Response:
        # if not self.is_connected():
        #     return create_error_response(ClientErrors.NOT_CONNECTED)
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rexec_recv(transaction)

        return resp_future

    def rexec_send(self, transaction: str, data: str) -> Response:
        # if not self.is_connected():
        #     return create_error_response(ClientErrors.NOT_CONNECTED)
        resp_future: Union[Response, Pyro4.futures.FutureResult] = \
            self.server.rexec_send(transaction, data)

        return resp_future

    def put(self) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.put()

    def put_next_info(self, transaction, finfo: FileInfo) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.put_next_info(transaction, finfo)

    def get(self, files: List[str]) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get(files)

    def get_next_info(self, transaction_id: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get_next_info(transaction_id)

    def _handle_response(self, resp: Response):
        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            self._destroy_connection()

    def _destroy_connection(self):
        log.d("Marking connection as disconnected")
        self._connected = False

        if self.server:
            log.d("Releasing pyro resource")
            self.server._pyroRelease()
            self.server = None
        else:
            log.w("Server already invalid, nothing to release")

