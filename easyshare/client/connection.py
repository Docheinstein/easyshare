from typing import cast, List

import Pyro4

from easyshare.client.errors import ClientErrors
from easyshare.protocol.response import Response, create_error_response, is_success_response
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.log import d
from easyshare.shared.trace import trace_out


class Connection:
    def __init__(self, server_info: ServerInfo):
        d("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: IServer = cast(IServer, Pyro4.Proxy(self.server_info.get("uri")))
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
        resp = self.server.open(sharing_name)

        if is_success_response(resp):
            self._connected = True
            self._sharing_name = sharing_name

        return resp

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

        trace_out(
            ip=self.server_info.get("ip"),
            port=self.server_info.get("port"),
            name=self.server_info.get("name"),
            what="RLS sort by {}{}".format(
                str(sort_by),
                " (reverse)" if reverse else ""
            )
        )
        return self.server.rls(sort_by, reverse=reverse)

    def rmkdir(self, directory) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def get(self, files) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get(files)

    def get_next(self, transaction) -> Response:
        if not self.is_connected():
            return create_error_response(ClientErrors.NOT_CONNECTED)

        return self.server.get_next(transaction)
