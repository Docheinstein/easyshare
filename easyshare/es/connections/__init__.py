from abc import ABC, abstractmethod

from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol import Response
from easyshare.protocol.responses import create_error_response, is_error_response, ServerErrors

log = get_logger(__name__)


def require_connected_connection(api):
    """
    Decorator for require the real connection before invoke an API.
    Raises a NOT_CONNECTED if is_connected() is False.
    """
    def require_connected_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("Checking esd connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("require_connected: not connected")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)

    require_connected_wrapper.__name__ = api.__name__

    return require_connected_wrapper


def handle_connection_response(api):
    """
    Decorator for handle the response and taking some fixed action
    e.g. destroy the connection in case of a NOT_CONNECTED response.
    """

    def handle_server_response_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("Invoking '%s' and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling '%s' response", api.__name__)
        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            log.e("Detected NOT_CONNECTED response, destroying connection")
            conn.destroy_connection()
        return resp

    handle_server_response_wrapper.__name__ = __name__

    return handle_server_response_wrapper



class Connection(ABC):
    """
    Base class for a connection with a remote service.
    """

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def destroy_connection(self):
        pass