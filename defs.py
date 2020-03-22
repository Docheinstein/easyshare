from abc import ABC, abstractmethod
from typing import Tuple

from server_response import ServerResponse

Address = Tuple[str, int]

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
    def rcd(self, path) -> ServerResponse:
        pass

    @abstractmethod
    def rls(self) -> ServerResponse:
        pass

    @abstractmethod
    def rmkdir(self, directory) -> ServerResponse:
        pass