from abc import ABC, abstractmethod

from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.services import Response
from easyshare.protocol.responses import create_error_response, is_error_response, ServerErrors

log = get_logger(__name__)


def require_connected_connection(api):
    """
    Decorator for require the real connection before invoke an API.
    Raises a NOT_CONNECTED if is_connected() is False.
    """
    def require_connected_wrapper(conn: 'Connection', *vargs, **kwargs) -> Response:
        log.d("require_connected_connection check before invoking '%s'", api.__name__)
        if not conn.is_connected():
            log.w("require_connected_connection: FAILED")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("require_connected_connection: OK - invoking '%s'", api.__name__)
        return api(conn, *vargs, **kwargs)

    require_connected_wrapper.__name__ = api.__name__

    return require_connected_wrapper


def handle_connection_response(api):
    """
    Decorator for handle the response and taking some standard actions.
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
    Base class for a connection with a remote 'Service'
    (which is a object published to a Pyro Daemon).
    """

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Whether this connection is connected.
        The meaning of 'connected' depends on the particular type of connection.
        e.g. a server connection is connected if it is authenticated.
        e.g. a sharing connection is connected if the sharing is actually open (and not closed yet)
        """
        pass

    @abstractmethod
    def destroy_connection(self):
        """ Destroy the connection; all the resources should be released (e.g. pyro proxy) """
        pass