from typing import List, Union


from easyshare.client.errors import ClientErrors
from easyshare.client.server import ServerProxy
from easyshare.protocol.response import Response, create_error_response, is_success_response
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.log import d


class Connection:
    def __init__(self, server_info: ServerInfo):
        d("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: Union[IServer, ServerProxy] = ServerProxy(server_info)
        self._connected = False
        self._sharing_name = None
        self._rpwd = ""

    def is_connected(self) -> bool:
        return self._connected

    def sharing_name(self) -> str:
        return self._sharing_name

    def rpwd(self) -> str:
        return self._rpwd

    def open(self, sharing_name: str) -> Response:
        # resp = self._perform_request("open", sharing_name)
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

        return self.server.rls(sort_by=sort_by, reverse=reverse)

    def rmkdir(self, directory) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def get_sharing(self, sharing_name: str) -> Response:
        # Allowed without a connection
        return self.server.get_sharing(sharing_name)

    def get_sharing_next_info(self, transaction_id: str) -> Response:
        # Allowed without a connection
        return self.server.get_sharing_next_info(transaction_id)

    def get_files(self, files: List[str]) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get_files(files)

    def get_files_next_info(self, transaction_id: str) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get_files_next_info(transaction_id)
