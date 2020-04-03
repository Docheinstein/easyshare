from abc import ABC, abstractmethod
from typing import Tuple, TypedDict

from server_response import ServerResponse

# (ip, port)
Endpoint = Tuple[str, int]


class FileInfo(TypedDict):
    name: str
    type: str
    size: int


class ServerIface(ABC):
    @abstractmethod
    def list(self) -> ServerResponse:
        pass

    @abstractmethod
    def open(self, sharing_name) -> ServerResponse:
        pass

    @abstractmethod
    def close(self) -> ServerResponse:
        pass

    @abstractmethod
    def rpwd(self) -> ServerResponse:
        pass

    @abstractmethod
    def rcd(self, path: str) -> ServerResponse:
        pass

    @abstractmethod
    def rls(self, sort_by="name") -> ServerResponse:
        pass

    @abstractmethod
    def rmkdir(self, directory) -> ServerResponse:
        pass

    @abstractmethod
    def get(self, files) -> ServerResponse:
        pass

    # @abstractmethod
    # def get_next(self, transaction) -> ServerResponse:
    #     pass

    @abstractmethod
    def get_next(self, transaction) -> ServerResponse:
        pass