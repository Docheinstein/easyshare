from abc import ABC, abstractmethod
from typing import List, Union

from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.overwrite import OverwritePolicy
from easyshare.protocol.response import Response


class ITransferService(ABC):
    @abstractmethod
    def outcome(self) -> Response:
        pass

    @abstractmethod
    def _run(self):
        pass


class IGetService(ITransferService):
    @abstractmethod
    def next(self, transfer: bool = False, skip: bool = False) -> Response:
        pass


class IPutService(ITransferService):
    class OverwritePolicy:
        PROMPT = 0
        YES = 1
        NO = 2
        NEWERT = 3
    @abstractmethod
    def next(self, finfo: Union[FileInfo, None],
             overwrite_policy: OverwritePolicy = OverwritePolicy.PROMPT) -> Response:
        pass


class IRexecService(ABC):
    class Event:
        TERMINATE = 0
        EOF = 1

    @abstractmethod
    def recv(self) -> Response:
        pass

    @abstractmethod
    def send_data(self, data: str) -> Response:
        pass

    @abstractmethod
    def send_event(self, ev: int) -> Response:
        pass


class ISharingService(ABC):
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
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        pass

    @abstractmethod
    def rtree(self, *,
              path: str = None, sort_by: List[str] = None,
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
    def get(self, files: List[str], check: bool) -> Response:
        pass

    @abstractmethod
    def put(self, check: bool = False) -> Response:
        pass


class IServer(ABC):
    @abstractmethod
    def connect(self, password: str) -> Response:
        """ New es"""
        pass

    @abstractmethod
    def disconnect(self) -> Response:
        pass

    @abstractmethod
    def list(self) -> Response:
        pass

    @abstractmethod
    def info(self) -> Response:
        pass

    @abstractmethod
    def open(self, sharing_name: str) -> Response:
        """ Opens a sharing """
        pass

    @abstractmethod
    def ping(self) -> Response:
        pass

    @abstractmethod
    def rexec(self, cmd: str) -> Response:
        pass