from typing import cast

import Pyro4

from easyshare.client.errors import ClientErrors
from easyshare.shared.log import t
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.response import Response, is_response_success, response_error, is_response_success_data


class Connection:
    def __init__(self, server_info):
        t("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: IServer = cast(IServer, Pyro4.Proxy(self.server_info["uri"]))
        self._connected = False
        self._sharing_name = None
        self._rpwd = ""

    def is_connected(self):
        return self._connected

    def sharing_name(self) -> str:
        return self._sharing_name

    def rpwd(self) -> str:
        return self._rpwd

    def open(self, sharing_name: str) -> Response:
        resp = self.server.open(sharing_name)

        if is_response_success(resp):
            self._connected = True
            self._sharing_name = sharing_name

        return resp

    def rcd(self, path) -> Response:
        if not self.is_connected():
            return response_error(ClientErrors.NOT_CONNECTED)

        resp = self.server.rcd(path)
        if is_response_success_data(resp):
            self._rpwd = resp["data"]

        return resp

    def rls(self, sort_by: str) -> Response:
        if not self.is_connected():
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.rls(sort_by)

    def rmkdir(self, directory) -> Response:
        if not self.is_connected():
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def get(self, files) -> Response:
        if not self.is_connected():
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.get(files)

    def get_next(self, transaction) -> Response:
        if not self.is_connected():
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.get_next(transaction)
