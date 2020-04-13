from abc import ABC, abstractmethod
from typing import List, Union

from easyshare.protocol.response import Response


class IServer(ABC):
    @abstractmethod
    def list(self) -> Response:
        pass

    @abstractmethod
    def open(self, sharing_name: str) -> Response:
        pass

    @abstractmethod
    def close(self) -> Response:
        pass

    @abstractmethod
    def rpwd(self) -> Response:
        pass

    @abstractmethod
    def rcd(self, path: str) -> Response:
        pass

    @abstractmethod
    def rls(self, sort_by: List[str], reverse=False) -> Response:
        pass

    @abstractmethod
    def rmkdir(self, directory: str) -> Response:
        pass

    @abstractmethod
    def get_sharing(self, sharing_name: str) -> Response:
        pass

    @abstractmethod
    def get(self, files: List[str]) -> Response:
        pass

    @abstractmethod
    def get_next(self, transaction) -> Response:
        pass
