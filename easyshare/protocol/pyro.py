from abc import ABC, abstractmethod
from typing import List, Union

import Pyro4

from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.response import Response

#
# class RexecCallback(ABC):
#     @abstractmethod
#     def stdout(self, line: str):
#         pass
#
#     @abstractmethod
#     def done(self, retcode: int):
#         pass


class IRexecTransaction(ABC):
    @abstractmethod
    def recv(self) -> Response:
        pass

    @abstractmethod
    def send(self, data: str) -> Response:
        pass


class IServer(ABC):
    @abstractmethod
    def open(self, sharing_name: str, password: str = None) -> Response:
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def rpwd(self) -> Response:
        pass

    @abstractmethod
    def rcd(self, path: str) -> Response:
        pass

    @abstractmethod
    def rls(self, *, path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        pass

    @abstractmethod
    def rtree(self, *,  path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None,) -> Response:
        pass

    @abstractmethod
    def rmkdir(self, directory: str) -> Response:
        pass

    @abstractmethod
    def rrm(self, paths: List[str]) -> Response:
        pass

    @abstractmethod
    def rmv(self, sources: List[str], destination: str) -> Response:
        pass

    @abstractmethod
    def rcp(self, sources: List[str], destination: str) -> Response:
        pass

    @abstractmethod
    def get(self, files: List[str]) -> Response:
        pass

    @abstractmethod
    def get_next_info(self, transaction) -> Response:
        pass

    @abstractmethod
    def put(self) -> Response:
        pass

    @abstractmethod
    def put_next_info(self, transaction, info: FileInfo) -> Response:
        pass

    @abstractmethod
    def ping(self) -> Response:
        pass

    @abstractmethod
    def rexec(self, cmd: str) -> Response:
        pass
    #
    # @abstractmethod
    # def rexec_recv(self, transaction: str) -> Response:
    #     pass
    #
    # @abstractmethod
    # def rexec_send(self, transaction: str, data: str) -> Response:
    #     pass
