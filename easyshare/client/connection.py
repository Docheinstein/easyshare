import ssl
from typing import List, Union, Optional

import Pyro4
from Pyro4 import socketutil
from Pyro4.core import _BatchProxyAdapter

from easyshare.client.errors import ClientErrors
from easyshare.client.server import ServerProxy
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.response import Response, create_error_response, is_success_response
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo


# def batchable(func):
#     def batchable_func(connection: 'Connection', *vargs, **kwargs) -> Response:
#         if connection._batch is None:
#             # Non batch
#             return func
#
#         log.i("Called method while in batch mode")
#         # Get the pyro wrapper for the method and call it
#         getattr(connection._batch, func.__name, *vargs, **kwargs)()
#
#     return batchable_func
#
from easyshare.utils.net import create_client_ssl_context


class Connection:

    RESPONSE_HANDLER_FUNC_NAME_PATTERN = "_handle_{}_response"

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

    def rpwd(self) -> str:
        return self._rpwd

    def open(self, sharing_name: str, password: str = None) -> Response:
        resp = self.server.open(sharing_name, password)

        if is_success_response(resp):
            self._connected = True
            self._sharing_name = sharing_name

        return resp

    def close(self):
        self.server.close() # async

        # noinspection PyProtectedMember
        self.server._pyroRelease()

        self._connected = False

    def rcd(self, path) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        resp = self.server.rcd(path)

        if is_success_response(resp):
            self._rpwd = resp["data"]

        return resp

    def rls(self, sort_by: List[str], reverse=False, path: str = None) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rls(sort_by, reverse=reverse, path=path)

    def rtree(self, sort_by: List[str], reverse=False, depth: int = int, path: str = None) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rtree(sort_by, reverse=reverse, depth=depth, path=path)

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
