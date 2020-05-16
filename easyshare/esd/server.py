import socket
import ssl
import threading

from Pyro5 import socketutil

from typing import Dict, Optional, cast

from Pyro5.api import expose, oneway
from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons.discover import get_discover_daemon, init_discover_daemon
from easyshare.esd.daemons.server import get_pyro_daemon, init_pyro_daemon
from easyshare.esd.daemons.transfer import get_transfer_daemon, init_transfer_daemon
from easyshare.esd.services.rexec import RexecService
from easyshare.esd.services.sharing import SharingService

from easyshare.logging import get_logger
from easyshare.auth import Auth, AuthNone
from easyshare.protocol import create_success_response, create_error_response, Response
from easyshare.protocol import ServerInfoFull, ServerInfo
from easyshare.common import DEFAULT_DISCOVER_PORT, ESD_PYRO_UID, DEFAULT_SERVER_PORT, transfer_port
from easyshare.endpoint import Endpoint
from easyshare.protocol import IServer
from easyshare.protocol import ServerErrors
from easyshare.ssl import set_ssl_context, get_ssl_context
from easyshare.tracing import trace_out
from easyshare.sockets import SocketUdpOut
from easyshare.styling import red, green
from easyshare.utils.json import json_to_bytes, j
from easyshare.utils.net import get_primary_ip, is_valid_port
from easyshare.utils.pyro.server import pyro_client_endpoint, try_or_command_failed_response, trace_api
from easyshare.utils.types import bytes_to_int

# ==================================================================

log = get_logger(__name__)



def require_client_connected(api):
    def require_client_connected_api(server: 'Server', *vargs, **kwargs):
        if not server._current_request_client():
            return create_error_response(ServerErrors.NOT_CONNECTED)
        return api(server, *vargs, **kwargs)

    require_client_connected_api.__name__ = api.__name__
    return require_client_connected_api


class Server(IServer):

    def __init__(self, *,
                 name: str = None,
                 address: str = None,
                 port: int = None,
                 discover_port: int = None,
                 auth: Auth = AuthNone(),
                 ssl_context: ssl.SSLContext = None,
                 rexec = False):
        self._name = name or socket.gethostname()
        self._port = port if port is not None else DEFAULT_SERVER_PORT
        self._discover_port = discover_port if discover_port is not None else DEFAULT_DISCOVER_PORT
        self._enable_discover_server = is_valid_port(self._discover_port)
        self._address = address or get_primary_ip()
        self._auth = auth
        self._rexec_enabled = rexec

        self._sharings: Dict[str, Sharing] = {}

        self._clients: Dict[Endpoint, ClientContext] = {}
        self._clients_lock = threading.Lock()

        # Discover daemon
        if self._enable_discover_server:
            init_discover_daemon(self._discover_port)
            get_discover_daemon().add_callback(
                self.handle_discover_request
            )

        # Transfer daemon
        init_transfer_daemon(transfer_port(self._port))

        # We don't have to listen to the transfer daemon
        # get and put services will do so

        set_ssl_context(ssl_context)
        self._ssl_context = get_ssl_context()

        init_pyro_daemon(
            address=self._address,
            port=self._port,
        )
        pyro_daemon = get_pyro_daemon()

        pyro_daemon.add_disconnection_callback(self._handle_client_disconnect)
        pyro_uri = str(pyro_daemon.register(self, ESD_PYRO_UID))

        address, port = self.endpoint()
        log.i("Server real address: %s", address)
        log.i("Server real port: %d", port)
        if self.is_discoverable():
            log.i("Server real discover address: %s", get_discover_daemon()._sock.address())
            log.i("Server real discover port: %d", get_discover_daemon()._sock.port())

        log.i("Server registered at URI: %s", pyro_uri)

    def add_sharing(self, sharing: Sharing):
        log.i("+ SHARING %s", str(sharing))
        self._sharings[sharing.name] = sharing

    def handle_discover_request(self, client_endpoint: Endpoint, data: bytes):
        log.i("<< DISCOVER %s", client_endpoint)
        log.i("Handling discover %s", str(data))


        response = create_success_response(self.server_info_full())

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            log.w("Invalid DISCOVER message received, ignoring it")
            return

        log.i("Client response port is %d", client_discover_response_port)

        # Respond to the port the es says in the paylod
        # (not necessary the one from which the request come)
        sock = SocketUdpOut()

        log.d("Sending DISCOVER response back to %s:%d\n%s",
              client_endpoint[0], client_discover_response_port,
              j(response))

        trace_out(
            "DISCOVER {}".format(j(response)),
            ip=client_endpoint[0],
            port=client_discover_response_port
        )

        sock.send(json_to_bytes(response), client_endpoint[0], client_discover_response_port)

    def start(self):
        th_discover = None


        th_pyro = threading.Thread(target=get_pyro_daemon().requestLoop, daemon=True)

        th_transfer = threading.Thread(target=get_transfer_daemon().run, daemon=True)

        if self.is_discoverable():
            th_discover = threading.Thread(target=get_discover_daemon().run, daemon=True)

        try:
            if th_discover:
                log.i("Starting DISCOVER daemon")
                th_discover.start()
            else:
                log.w("NOT starting DISCOVER daemon")

            log.i("Starting PYRO daemon")
            th_pyro.start()

            log.i("Starting TRANSFER daemon")
            th_transfer.start()

            log.i("Ready to handle requests")

            if th_discover:
                th_discover.join()
            th_pyro.join()
            th_transfer.join()

        except KeyboardInterrupt:
            log.d("CTRL+C detected; quitting")
            # Formally not a clean quit, but who cares we are exiting...

        log.i("FINISH")

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

        self._add_client(client_endpoint)

        return create_success_response()


    @expose
    @oneway
    @trace_api
    @require_client_connected
    @try_or_command_failed_response
    def disconnect(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< DISCONNECT [%s]", client_endpoint)

        if self._del_client(self._current_request_endpoint()):
            log.i("Client disconnected gracefully")
        else:
            # Should not happen due @require_client_connected
            log.w("disconnect() failed; es not found")


    @expose
    @trace_api
    @try_or_command_failed_response
    # @require_client_connected
    def list(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< LIST [%s]", client_endpoint)

        return create_success_response([sh.info() for sh in self._sharings.values()])

    @expose
    @trace_api
    @try_or_command_failed_response
    # @require_client_connected
    def info(self):
        client_endpoint = self._current_request_endpoint()

        log.i("<< INFO [%s]", client_endpoint)

        return create_success_response(
            self.server_info()
        )


    @expose
    @trace_api
    @require_client_connected
    @try_or_command_failed_response
    def open(self, sharing_name: str) -> Response:
        if not sharing_name:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        sharing = self._sharings.get(sharing_name)

        if not sharing:
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        client = self._current_request_client()

        log.i("<< OPEN %s [%s]", sharing_name, client)

        serving = SharingService(
            server_port=self._port,
            sharing=sharing,
            sharing_rcwd="",
            client=client,
            end_callback=lambda cs: cs.unpublish()
        )

        uid = serving.publish()

        log.i("Opened sharing UID: %s", uid)

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
            log.e("Client attempted remote command execution; denying since rexec is disabled")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i(">> REXEC %s [%s]", cmd, client)

        rx = RexecService(
            cmd,
            client=client,
            end_callback=lambda cs: cs.unpublish()
        )
        rx.run()

        uri = rx.publish()

        log.d("Rexec handler initialized; uri: %s", uri)
        return create_success_response(uri)

    def server_info(self) -> ServerInfo:
        si = {
            "name": self._name,
            "sharings": [sh.info() for sh in self._sharings.values()],
            "ssl": True if self._ssl_context else False,
            "auth": True if (self._auth and self._auth.algo_security() > 0) else False
        }

        return si


    def server_info_full(self) -> ServerInfoFull:
        si: ServerInfoFull = cast(ServerInfoFull, self.server_info())
        si["ip"] = self.endpoint()[0]
        si["port"] = self.endpoint()[1]

        si["discoverable"] = self._enable_discover_server

        if self._enable_discover_server:
            si["discover_port"] = get_discover_daemon().endpoint()[1]
        return si

    def _add_client(self, endpoint: Endpoint) -> ClientContext:
        with self._clients_lock:
            ctx = ClientContext(endpoint)

            log.i("Adding es %s", ctx)

            print(green("Client connected: {}:{}".format(ctx.endpoint[0], ctx.endpoint[1])))

            self._clients[endpoint] = ctx

        return ctx

    def _del_client(self, endpoint: Endpoint) -> bool:
        with self._clients_lock:
            ctx = self._clients.pop(endpoint, None)

            if not ctx:
                return False

            print(red("Client disconnected: {}:{}".format(ctx.endpoint[0], ctx.endpoint[1])))

            log.i("Removing es %s", ctx)

            daemon = get_pyro_daemon()

            with ctx.lock:
                for service_id in ctx.services:
                    daemon.unpublish(service_id)


        return True

    def _current_request_endpoint(self) -> Optional[Endpoint]:
        """
        Returns the endpoint (ip, port) of the es that is making
        the request right now (provided by the underlying Pyro deamon)
        :return: the endpoint of the current es
        """
        return pyro_client_endpoint()

    def _current_request_client(self) -> Optional[ClientContext]:
        """
        Returns the es that belongs to the current request endpoint (ip, port)
        if exists among the known clients; otherwise returns None.
        :return: the es of the current request
        """
        return self._clients.get(self._current_request_endpoint())

    def endpoint(self) -> Endpoint:
        """
        Returns the current endpoint (ip, port) the esd (Pyro deamon) is bound to.
        :return: the current esd endpoint
        """
        return get_pyro_daemon().sock.getsockname()

    def name(self) -> str:
        return self._name

    def auth_type(self) -> str:
        return self._auth.algo_type()

    def is_rexec_enabled(self) -> bool:
        return self._rexec_enabled

    def is_discoverable(self) -> bool:
        return self._enable_discover_server

    def _handle_client_disconnect(self, pyroconn: socketutil.SocketConnection):
        endpoint = pyroconn.sock.getpeername()
        log.d("Cleaning up es %s resources", endpoint)
        self._del_client(endpoint)
