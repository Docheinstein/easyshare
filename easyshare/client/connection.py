from typing import List, Union, Optional

import Pyro4
from Pyro4.core import _BatchProxyAdapter

from easyshare.client.errors import ClientErrors
from easyshare.client.server import ServerProxy
from easyshare.protocol.response import Response, create_error_response, is_success_response
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.log import d, v
from easyshare.utils.json import json_to_pretty_str


# def batchable(func):
#     def batchable_func(connection: 'Connection', *vargs, **kwargs) -> Response:
#         if connection._batch is None:
#             # Non batch
#             return func
#
#         v("Called method while in batch mode")
#         # Get the pyro wrapper for the method and call it
#         getattr(connection._batch, func.__name, *vargs, **kwargs)()
#
#     return batchable_func
#

class Connection:

    RESPONSE_HANDLER_FUNC_NAME_PATTERN = "_handle_{}_response"

    def __init__(self, server_info: ServerInfo):
        d("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: Union[IServer, ServerProxy] = ServerProxy(server_info)
        self._connected = False
        self._sharing_name = None
        self._rpwd = ""

        self._batch: Optional[_BatchProxyAdapter] = None
    #
    # def start_batch(self):
    #     self._batch = Pyro4.batch(self.server)
    #
    # def exec_batch(self) -> Optional[List[Response]]:
    #     if not self._batch:
    #         return None
    #
    #     # Retrieve the calls params
    #     calls = list(self._batch._BatchProxyAdapter__calls)
    #     d("Batch calls: %s", calls)
    #
    #     # Execute the calls
    #     responses_generator = self._batch()
    #     responses = []
    #
    #     for idx, resp in enumerate(responses_generator):
    #         funcname, funcargs, funckwargs = calls[idx]
    #
    #         d("Got batch response for request '%s': \n%s",
    #           funcname,
    #           json_to_pretty_str(resp)
    #         )
    #
    #         # Eventually handle the response
    #         handler_func_name = Connection.RESPONSE_HANDLER_FUNC_NAME_PATTERN.format(funcname)
    #         if hasattr(self, handler_func_name):
    #             d("Found a response handler, passing response to it")
    #             getattr(self, handler_func_name)(funcargs, funckwargs)
    #
    #         responses.append(resp)
    #
    #     return responses

    def is_connected(self) -> bool:
        return self._connected

    def sharing_name(self) -> str:
        return self._sharing_name

    def rpwd(self) -> str:
        return self._rpwd

    def open(self, sharing_name: str) -> Response:
        resp = self.server.open(sharing_name)

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

    def rls(self, sort_by: List[str], reverse=False) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rls(sort_by, reverse=reverse)

    def rtree(self, sort_by: List[str], reverse=False, depth: int = int) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rtree(sort_by, reverse=reverse, depth=depth)

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

    def get(self, files: List[str]) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get(files)

    def get_next_info(self, transaction_id: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get_next_info(transaction_id)
