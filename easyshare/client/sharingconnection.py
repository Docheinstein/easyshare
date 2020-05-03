from typing import Union


from easyshare.client.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.response import Response, create_error_response, is_success_response, is_data_response, \
    is_error_response
from easyshare.protocol.pyro import IServing
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.sharinginfo import SharingInfo
from easyshare.utils.pyro import TracedPyroProxy

log = get_logger(__name__)


def require_sharing_connection(api):
    def require_sharing_connection_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Checking sharing connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("@require_sharing_connection : invalid connection")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Sharing connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)
    return require_sharing_connection_api_wrapper


def handle_sharing_response(api):
    def handle_sharing_response_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Invoking %s and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling %s response", api.__name__)

        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            conn._destroy_connection()

        return resp

    return handle_sharing_response_api_wrapper


class SharingConnection:

    def __init__(self, sharing_uri: str, sharing_info: SharingInfo, server_info: ServerInfo = None):
        log.d("Initializing new SharingConnection")
        self.sharing_info: SharingInfo = sharing_info
        self.server_info: ServerInfo = server_info

        self._connected = True
        self._rcwd = ""

        # Create the proxy for the remote sharing
        self.serving: Union[IServing, TracedPyroProxy] = TracedPyroProxy(
            sharing_uri,
            alias="{}{}{}".format(
                sharing_info.get("name") if sharing_info else "",
                "@" if server_info and sharing_info else "",
                server_info.get("name") if server_info else ""
            )
        )

    def is_connected(self) -> bool:
        return self._connected is True and self.serving

    def sharing_name(self) -> str:
        return self.sharing_info.get("name")

    def rcwd(self) -> str:
        return self._rcwd

    # =====

    # NO @handle_response (async)
    @require_sharing_connection
    def close(self):
        self.serving.close()         # async
        self._destroy_connection()

    #
    # def rpwd(self) -> str:
    #     return self._rpwd
    #
    # @handle_response
    # @require_connection
    # def rcd(self, path) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rcd(path)
    #
    #     resp = resp_future.value
    #
    #     if is_success_response(resp):
    #         self._rpwd = resp["data"]
    #
    #     return resp
    #
    # @handle_response
    # @require_connection
    # def rls(self, sort_by: List[str], reverse: bool = False,
    #         hidden: bool = False,  path: str = None) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rls(path=path, sort_by=sort_by,
    #                         reverse=reverse, hidden=hidden)
    #     return resp_future
    #     # return resp_future.value
    #
    # @handle_response
    # @require_connection
    # def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
    #           max_depth: int = int, path: str = None) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rtree(path=path, sort_by=sort_by, reverse=reverse,
    #                           hidden=hidden, max_depth=max_depth)
    #
    #     return resp_future.value
    #
    # @handle_response
    # @require_connection
    # def rmkdir(self, directory) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rmkdir(directory)
    #
    #     return resp_future.value
    #
    # @handle_response
    # @require_connection
    # def rrm(self, paths: List[str]) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rrm(paths)
    #
    #     return resp_future.value
    #
    # @handle_response
    # @require_connection
    # def rmv(self, sources: List[str], destination: str) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rmv(sources, destination)
    #
    #     return resp_future.value
    #
    # @handle_response
    # @require_connection
    # def rcp(self, sources: List[str], destination: str) -> Response:
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rcp(sources, destination)
    #
    #     return resp_future.value
    #
    # def ping(self) -> Response:
    #     # if not self.is_connected():
    #     #     return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     return self.server.ping()
    #
    # # def rexec(self, cmd: str) -> Response:
    # def rexec(self, cmd: str) -> Response:
    #     # if not self.is_connected():
    #     #     return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rexec(cmd)
    #
    #     return resp_future
    #
    # def rexec_recv(self, transaction: str) -> Response:
    #     # if not self.is_connected():
    #     #     return create_error_response(ClientErrors.NOT_CONNECTED)
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rexec_recv(transaction)
    #
    #     return resp_future
    #
    # def rexec_send(self, transaction: str, data: str) -> Response:
    #     # if not self.is_connected():
    #     #     return create_error_response(ClientErrors.NOT_CONNECTED)
    #     resp_future: Union[Response, Pyro4.futures.FutureResult] = \
    #         self.server.rexec_send(transaction, data)
    #
    #     return resp_future
    #
    # def put(self) -> Response:
    #     if not self.is_connected():
    #         return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     return self.server.put()
    #
    # def put_next_info(self, transaction, finfo: FileInfo) -> Response:
    #     if not self.is_connected():
    #         return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     return self.server.put_next_info(transaction, finfo)
    #
    # def get(self, files: List[str]) -> Response:
    #     if not self.is_connected():
    #         return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     return self.server.get(files)
    #
    # def get_next_info(self, transaction_id: str) -> Response:
    #     if not self.is_connected():
    #         return create_error_response(ClientErrors.NOT_CONNECTED)
    #
    #     return self.server.get_next_info(transaction_id)
    #
    # def _handle_response(self, resp: Response):
    #     if is_error_response(resp, ServerErrors.NOT_CONNECTED):
    #         self._destroy_connection()

    def _destroy_connection(self):
        log.d("Marking sharing connection as disconnected")
        self._connected = False

        if self.serving:
            log.d("Releasing sharing connection's pyro resource")
            self.serving._pyroRelease()
            self.serving = None
        else:
            log.w("Sharing connection already invalid, nothing to release")

