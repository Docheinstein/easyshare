from abc import ABC, abstractmethod
from typing import Union

from easyshare.consts import ansi
from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.services import Response
from easyshare.protocol.responses import create_error_response, is_error_response, ServerErrors
from easyshare.utils.inspection import stacktrace

log = get_logger(__name__)




class Connection(ABC):
    """
    Base class for a connection with a remote 'Service'
    (which is a object published to a Pyro Daemon).
    """

    @abstractmethod
    def is_established(self) -> bool:
        """
        Whether this connection is connected.
        The meaning of 'connected' depends on the particular type of connection.
        e.g. a server connection is connected if it is authenticated.
        e.g. a sharing connection is connected if the sharing is actually open (and not closed yet)
        """
        pass

    @abstractmethod
    def destroy(self):
        """ Destroy the connection; all the resources should be released (e.g. pyro proxy) """
        pass

    @abstractmethod
    def write(self, data: Union[bytes, bytearray]):
        pass

    @abstractmethod
    def read(self) -> bytearray:
        pass