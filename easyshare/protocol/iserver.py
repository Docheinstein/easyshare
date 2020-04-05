from abc import ABC, abstractmethod

from easyshare.protocol.response import Response


class IServer(ABC):
    @abstractmethod
    def list(self) -> Response:
        pass

    @abstractmethod
    def open(self, sharing_name) -> Response:
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
    def rls(self, sort_by="name") -> Response:
        pass

    @abstractmethod
    def rmkdir(self, directory) -> Response:
        pass

    @abstractmethod
    def get(self, files) -> Response:
        pass

    # @abstractmethod
    # def get_next(self, transaction) -> ServerResponse:
    #     pass

    @abstractmethod
    def get_next(self, transaction) -> Response:
        pass