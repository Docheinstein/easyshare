from easyshare.protocol.types import OverwritePolicy, FileInfo
from typing import List, Union
from easyshare.protocol.responses import Response

from abc import ABC, abstractmethod


# ================================================
# ============= EXPOSED PYRO OBJECTS =============
# ================================================


class IServer(ABC):
    """ Main server interface """

    @abstractmethod
    def connect(self, password: str) -> Response:
        """
        Establish the connection with the server,
        adding the client to the set of known clients.
        """
        pass

    @abstractmethod
    def disconnect(self) -> Response:
        """
        Disconnect from the server for which
        connect() has been called previously.
        """
        pass

    @abstractmethod
    def list(self) -> Response:
        """ Lists the sharings of the server """
        pass

    @abstractmethod
    def info(self) -> Response:
        """ Get server info """
        pass

    @abstractmethod
    def open(self, sharing_name: str) -> Response:
        """
        Open the sharing with the given 'sharing_name'
        and instantiate a 'SharingService' the client can
        access for perform operations on the sharing.
        """
        pass

    @abstractmethod
    def ping(self) -> Response:
        """
        Asks the server to respond PONG.
        """
        pass

    @abstractmethod
    def rexec(self, cmd: str) -> Response:
        """
        Execute the command cmd on the server, instantiate a 'RexecService'
        the client can access for receive stdout and send stdin.
        Currently works only if the remote server is Unix based.
        """
        pass

    @abstractmethod
    def rshell(self, cmd: str) -> Response:
        """
        Execute a remote shell on the server, instantiate a 'RshellService'
        the client can access for receive stdout and send stdin.
        Currently works only if the remote server is Unix based.
        """
        pass


class ITransferService(ABC):
    """ Base interface of a general transfer command (get/put) """

    @abstractmethod
    def outcome(self) -> Response:
        """ Get or wait for an outcome of the transfer process """
        pass


class IGetService(ITransferService):
    """ Interface of the get command service bound to a client """

    @abstractmethod
    def next(self, transfer: bool = False, skip: bool = False) -> Response:
        """ Retrieve the info of the next file to pull """
        pass


class IPutService(ITransferService):
    """ Interface of the put command service bound to a client """

    @abstractmethod
    def next(self, finfo: Union[FileInfo, None],
             overwrite_policy: OverwritePolicy = OverwritePolicy.PROMPT) -> Response:
        """ Send the info of the next file to push """
        pass


class IRexecService(ABC):
    """ Interface of the rexec command service bound to a client """

    class Event:
        TERMINATE = 0
        EOF = 1

    @abstractmethod
    def recv(self) -> Response:
        """
        When available, receive lines from stdout
        and stderr of the remote process
        """
        pass

    @abstractmethod
    def send_data(self, data: str) -> Response:
        """ Send data to the stdin of the remote process """
        pass

    @abstractmethod
    def send_event(self, ev: int) -> Response:
        """ Send a signal to the remote process """
        pass


class IRshellService(ABC):
    """ Interface of the rshell command service bound to a client """

    class Event:
        TERMINATE = 0
        EOF = 1

    @abstractmethod
    def recv(self) -> Response:
        """
        When available, receive lines from stdout
        and stderr of the remote process
        """
        pass

    @abstractmethod
    def send_data(self, data: str) -> Response:
        """ Send data to the stdin of the remote process """
        pass

    @abstractmethod
    def send_event(self, ev: int) -> Response:
        """ Send a signal to the remote process """
        pass


class ISharingService(ABC):
    """ Interface of a sharing service (sharing opened by a client) """

    @abstractmethod
    def close_(self): # can't call this close() due to a
                      # pyro conflict for resources tracking
        """ Close the sharing, destroying the 'SharingService' """
        pass

    @abstractmethod
    def rpwd(self) -> Response:
        """ Remote working directory """
        pass

    @abstractmethod
    def rcd(self, path: str) -> Response:
        """ Change current remote directory """
        pass

    @abstractmethod
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        """ List files remotely """
        pass

    @abstractmethod
    def rtree(self, *,
              path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None,) -> Response:
        """ Get a tree representation of the remote directory """
        pass

    @abstractmethod
    def rmkdir(self, directory: str) -> Response:
        """ Create directory remotely """
        pass

    @abstractmethod
    def rrm(self, paths: List[str]) -> Response:
        """ Remove files remotely """
        pass

    @abstractmethod
    def rmv(self, sources: List[str], destination: str) -> Response:
        """ Move files remotely """
        pass

    @abstractmethod
    def rcp(self, sources: List[str], destination: str) -> Response:
        """ Copy files remotely """
        pass

    @abstractmethod
    def get(self, files: List[str], check: bool) -> Response:
        """ Start a get transfer, which instantiate a 'GetService' """
        pass

    @abstractmethod
    def put(self, check: bool = False) -> Response:
        """ Start a put transfer, which instantiate a 'PutService' """
        pass
