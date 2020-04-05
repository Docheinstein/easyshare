import os
from typing import Union, Any

import Pyro4

from easyshare.client.errors import ClientErrors
from easyshare.shared.log import t
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.response import Response, is_response_success, response_error


class Connection:
    def __init__(self, server_info):
        t("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: Union[IServer, Any] = Pyro4.Proxy(self.server_info["uri"])
        self._connected = False
        self._sharing = None
        self._rpwd = ""

    def is_connected(self):
        return self._connected

    def rpwd(self):
        return os.path.join(self._sharing,
                            self._rpwd).rstrip(os.sep)

    def open(self, sharing) -> Response:
        resp = self.server.open(sharing)

        if is_response_success(resp):
            self._connected = True
            self._sharing = sharing

        return resp

    def rcd(self, path) -> Response:
        if not self._connected:
            return response_error(ClientErrors.NOT_CONNECTED)

        resp = self.server.rcd(path)
        if is_response_success(resp):
            self._rpwd = resp["data"]

        return resp

    def rls(self, sort_by: str) -> Response:
        if not self._connected:
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.rls(sort_by)

    def rmkdir(self, directory) -> Response:
        if not self._connected:
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def get(self, files) -> Response:
        if not self._connected:
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.get(files)

    def get_next(self, transaction) -> Response:
        if not self._connected:
            return response_error(ClientErrors.NOT_CONNECTED)

        return self.server.get_next(transaction)
