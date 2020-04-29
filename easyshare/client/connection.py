from typing import List, Union


from easyshare.client.errors import ClientErrors
from easyshare.client.server import ServerProxy
from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.response import Response, create_error_response, is_success_response, is_data_response, \
    is_error_response
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo


log = get_logger(__name__)


def require_connection(api):
    def require_connection_api_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("Checking connection before invoking %s", api.__name__)
        if not conn.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Connection OK, invoking %s", api.__name__)
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

    def is_connected(self) -> bool:
        return self._connected

    def sharing_name(self) -> str:
        return self._sharing_name

    def open(self, sharing_name: str, password: str = None) -> Response:
        resp = self.server.open(sharing_name, password)

        if is_success_response(resp):
            self._connected = True
            self._sharing_name = sharing_name

        return resp

    def close(self):
        self.server.close()     # async
        self._destroy_connection()

    def rpwd(self) -> str:
        return self._rpwd

    @handle_response
    @require_connection
    def rcd(self, path) -> Response:
        resp = self.server.rcd(path)

        if is_success_response(resp):
            self._rpwd = resp["data"]

        return resp

    @handle_response
    @require_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False,  path: str = None) -> Response:
        return self.server.rls(path=path, sort_by=sort_by,
                               reverse=reverse, hidden=hidden)

    @handle_response
    @require_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, path: str = None) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rtree(path=path, sort_by=sort_by, reverse=reverse,
                                 hidden=hidden, max_depth=max_depth)

    def rmkdir(self, directory) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def rrm(self, paths: List[str]) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rrm(paths)

    def rcp(self, sources: List[str], destination: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rcp(sources, destination)

    def rmv(self, sources: List[str], destination: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rmv(sources, destination)

    def ping(self) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.ping()

    def rexec(self, cmd: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rexec(cmd)

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
        log.d("Destroy connection (releasing pyro resources)")
        self._connected = False
        self.server._pyroRelease()
        self.server = None

