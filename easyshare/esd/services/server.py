import threading
from typing import Dict, Optional, List

from Pyro5 import socketutil
from Pyro5.api import expose, oneway

from easyshare.common import ESD_PYRO_UID
from easyshare.endpoint import Endpoint
from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons.pyro import get_pyro_daemon
from easyshare.esd.services import BaseService
from easyshare.esd.services.rexec import RexecService
from easyshare.esd.services.rshell import RshellService
from easyshare.esd.services.sharing import SharingService
from easyshare.logging import get_logger
from easyshare.protocol.services import IServer
from easyshare.protocol.responses import ServerErrors, create_error_response, create_success_response, Response
from easyshare.protocol.types import ServerInfo
from easyshare.styling import red, green
from easyshare.utils.pyro.server import pyro_client_endpoint, try_or_command_failed_response, trace_api
from easyshare.utils.str import q

log = get_logger(__name__)


# =============================================
# ============== SERVER SERVICE ===============
# =============================================


def require_connected_client(api):
    """
    Decorator for require that the client that performs the request is actually
    connected at application level (i.e. authenticated).
    Raises a NOT_CONNECTED if the client is not connected.
    """
    def require_connected_client_wrapper(server: 'ServerService', *vargs, **kwargs):
        if not server._current_request_client():
            return create_error_response(ServerErrors.NOT_CONNECTED)
        return api(server, *vargs, **kwargs)

    require_connected_client_wrapper.__name__ = api.__name__

    return require_connected_client_wrapper


class ServerService(IServer, BaseService):
    """
    Implementation of 'IServer' interface that will be published with Pyro.
    Offers all the methods that operate on a server (e.g. open, ping, rexec).
    """

    def __init__(self, *,
                 sharings: List[Sharing],
                 name,
                 address,
                 port,
                 auth,
                 rexec):
        self._sharings = {s.name: s for s in sharings}
        self._name = name
        self._port = port
        self._address = address
        self._auth = auth
        self._rexec_enabled = rexec


        self._clients: Dict[Endpoint, ClientContext] = {}
        self._clients_lock = threading.Lock()

        self.published = False

    def publish(self) -> str:
        """ Publishes the service to the Pyro Daemon """
        get_pyro_daemon().add_disconnection_callback(self._handle_client_disconnect)
        uri, uid = get_pyro_daemon().publish(self, uid=ESD_PYRO_UID)
        self.published = True

        log.i(f"ServerService registered at URI: {uri}")

        return uid

    def unpublish(self):
        """ Unpublishes the service from the Pyro Daemon """
        get_pyro_daemon().unpublish(ESD_PYRO_UID)
        self.published = False

    def is_published(self) -> bool:
        """ Whether the service is published """
        return self.published

    def endpoint(self) -> Endpoint:
        return get_pyro_daemon().sock.getsockname()

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

    def name(self) -> str:
        """ Name of the server"""
        return self._name

    def auth_type(self) -> str:
        """ Authentication type """
        return self._auth.algo_type()

    def is_rexec_enabled(self) -> bool:
        """ Whether rexec is enabled """
        return self._rexec_enabled

    @expose
    @trace_api
    @try_or_command_failed_response
    def connect(self, password: str = None) -> Response:
        client_endpoint = self._current_request_endpoint()
        client = self._current_request_client()

        log.i("<< CONNECT [%s]", client_endpoint)

        if client:
            log.w("Client already connected")
            return create_success_response()

        # Authentication
        log.i("Authentication check - type: %s", self._auth.algo_type())

        # Just ask the auth whether it matches or not
        # (The password can either be none/plain/hash, the auth handles them all)
        if not self._auth.authenticate(password):
            log.e("Authentication FAILED")
            return create_error_response(ServerErrors.AUTHENTICATION_FAILED)
        else:
            log.i("Authentication OK")

        ctx = self._add_client_endpoint(client_endpoint)

        print(green(f"[{ctx.tag}] connected - {ctx.endpoint[0]}"))

        return create_success_response()


    @expose
    @oneway
    @trace_api
    @require_connected_client
    @try_or_command_failed_response
    def disconnect(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< DISCONNECT [%s]", client_endpoint)

        if self._del_client(self._current_request_endpoint()):
            log.i("Client disconnected gracefully")
        else:
            # Should not happen due @require_client_connected
            log.w("disconnect() failed; client not found")


    @expose
    @trace_api
    @try_or_command_failed_response
    # NO @require_client_connected
    def list(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< LIST [%s]", client_endpoint)

        return create_success_response([sh.info() for sh in self._sharings.values()])

    @expose
    @trace_api
    @try_or_command_failed_response
    # NO @require_client_connected
    def info(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< INFO [%s]", client_endpoint)

        return create_success_response(
            self.server_info()
        )


    @expose
    @trace_api
    @require_connected_client
    @try_or_command_failed_response
    def open(self, sharing_name: str) -> Response:
        if not sharing_name:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        sharing: Sharing = self._sharings.get(sharing_name)

        if not sharing:
            return create_error_response(ServerErrors.SHARING_NOT_FOUND, q(sharing_name))

        client = self._current_request_client()

        log.i("<< OPEN %s [%s]", sharing_name, client)

        serving = SharingService(
            server_port=self._port,
            sharing=sharing,
            sharing_rcwd=sharing.path,
            client=client,
            conn_callback=lambda cs: self._add_endpoint_for_client(cs.endpoint, cs.client),
            end_callback=lambda cs: cs.unpublish()
        )

        uid = serving.publish()

        log.i("Opened sharing UID: %s", uid)

        print(f"[{client.tag}] open '{sharing_name}'")

        return create_success_response(uid)


    @expose
    @trace_api
    @try_or_command_failed_response
    # @require_client_connected
    def ping(self):
        return create_success_response("pong")

    @expose
    @trace_api
    @try_or_command_failed_response
    def rexec(self, cmd: str) -> Response:
        if not self._rexec_enabled:
            log.w("Client attempted remote command execution; denying since rexec is disabled")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i(">> REXEC %s [%s]", cmd, client)

        rx = RexecService(
            cmd,
            client=client,
            conn_callback=lambda cs: self._add_endpoint_for_client(cs.endpoint, cs.client),
            end_callback=lambda cs: cs.unpublish()
        )
        rx.run()

        uri = rx.publish()

        log.d("Rexec handler initialized; uri: %s", uri)

        print(f"[{client.tag}] rexec '{cmd}'")

        return create_success_response(uri)

    @expose
    @trace_api
    @try_or_command_failed_response
    def rshell(self) -> Response:
        if not self._rexec_enabled:
            log.w("Client attempted remote command execution; denying since rexec is disabled")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i(">> RSHELL [%s]", client)

        rsh = RshellService(
            client=client,
            conn_callback=lambda cs: self._add_endpoint_for_client(cs.endpoint, cs.client),
            end_callback=lambda cs: cs.unpublish()
        )
        rsh.run()

        uri = rsh.publish()

        log.d("Rexec handler initialized; uri: %s", uri)

        print(f"[{client.tag}] rshell")

        return create_success_response(uri)

    def server_info(self) -> ServerInfo:
        """ Returns a 'ServerInfo' of this server service"""
        si = {
            "name": self._name,
            "sharings": [sh.info() for sh in self._sharings.values()],
            "ssl": get_pyro_daemon().has_ssl(),
            "auth": True if (self._auth and self._auth.algo_security() > 0) else False
        }

        return si

    def _add_endpoint_for_client(self, endpoint: Endpoint, client: ClientContext = None):
        self._add_client_endpoint(endpoint, client)

    def _add_client_endpoint(self, endpoint: Endpoint, client: ClientContext = None) -> ClientContext:
        """
        Adds the endpoint to the set of known clients' endpoints.
        (Each service has a different endpoint, we have to store all the associations)
         """
        if not client:
            client = ClientContext(endpoint)

        with self._clients_lock:
            self._clients[endpoint] = client

        log.i("New client for endpoint %s", endpoint)

        return client


    def _del_client_endpoint(self, endpoint: Endpoint) -> ClientContext:
        """
        Removes the endpoint from the set of known clients
        and cleanups associated resources
        """
        with self._clients_lock:
            ctx = self._clients.pop(endpoint, None)

        if ctx:
            log.d("Removed endpoint %s from client %s", endpoint, ctx)

        return ctx

    def _del_client(self, endpoint: Endpoint) -> bool:
        """
        Removes the endpoint from the set of known clients
        and cleanups associated resources
        """
        ctx = self._del_client_endpoint(endpoint)

        if ctx:
            daemon = get_pyro_daemon()

            with ctx.lock:
                for service_id in ctx.services:
                    daemon.unpublish(service_id)

        if ctx:
            print(red(f"[{ctx.tag}] disconnected - {ctx.endpoint[0]}"))
        else:
            log.w("No client to remove for endpoint %s", endpoint)

        return True

    def _current_request_endpoint(self) -> Optional[Endpoint]:
        """
        Returns the endpoint (ip, port) of the client that is making
        the request right now (provided by the underlying Pyro deamon)
        """
        return pyro_client_endpoint()

    def _current_request_client(self) -> Optional[ClientContext]:
        """
        Returns the client that belongs to the current request endpoint (ip, port)
        if exists among the known clients; otherwise returns None.
        """
        return self._clients.get(self._current_request_endpoint())

    def _handle_client_disconnect(self, pyroconn: socketutil.SocketConnection):
        """
        Callbacke invoked by pyro when a client disconnects:
        cleanup the client's resources
        """
        endpoint = pyroconn.sock.getpeername()
        log.d("Cleaning up client %s resources", endpoint)
        self._del_client_endpoint(endpoint)
