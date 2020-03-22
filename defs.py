from abc import ABC, abstractmethod


class EasyshareServerIface(ABC):
    @abstractmethod
    def list(self):
        pass

    @abstractmethod
    def open(self, sharing_name):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def rpwd(self):
        pass

    @abstractmethod
    def rcd(self, path):
        pass

class EasyshareServerResponseCode:
    OK = 0
    NOT_CONNECTED = -1
    INVALID_COMMAND_SYNTAX = -2
    SHARING_NOT_FOUND = -3