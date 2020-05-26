import socket
import ssl
import threading
from typing import cast, List

from easyshare.auth import Auth, AuthNone
from easyshare.common import DEFAULT_DISCOVER_PORT, DEFAULT_SERVER_PORT, transfer_port
from easyshare.consts.net import ADDR_ANY
from easyshare.endpoint import Endpoint
from easyshare.esd.common import Sharing
from easyshare.esd.daemons.discover import get_discover_daemon, init_discover_daemon
from easyshare.esd.daemons.pyro import get_pyro_daemon, init_pyro_daemon
from easyshare.esd.daemons.transfer import get_transfer_daemon, init_transfer_daemon
from easyshare.esd.services.server import ServerService
from easyshare.logging import get_logger
from easyshare.protocol.responses import create_success_response
from easyshare.protocol.types import ServerInfoFull
from easyshare.sockets import SocketUdpOut
from easyshare.ssl import set_ssl_context
from easyshare.tracing import trace_out
from easyshare.utils.json import json_to_bytes, j
from easyshare.utils.net import get_primary_ip, is_valid_port
from easyshare.utils.types import bytes_to_int


log = get_logger(__name__)


class Server:
    """
    Server of esd that aggregates three daemons: server, transfer, discover.
    """
    def __init__(self, *,
                 sharings: List[Sharing],
                 name: str = None,
                 address: str = None,
                 port: int = None,
                 discover_port: int = None,
                 auth: Auth = AuthNone(),
                 ssl_context: ssl.SSLContext = None,
                 rexec = False):
        address = address or get_primary_ip()
        port = port if port is not None else DEFAULT_SERVER_PORT
        discover_port = discover_port if discover_port is not None else DEFAULT_DISCOVER_PORT

        # First of all set the SSL context since is used by all the daemons
        # (transfer and pyro actually, discover no since is UDP)
        set_ssl_context(ssl_context)

        # === DISCOVER DAEMON ===
        discover_daemon = None

        if is_valid_port(discover_port):
            discover_daemon = init_discover_daemon(
                port=discover_port
            )
            discover_daemon.add_callback(
                self._handle_discover_request
            )

        # === TRANSFER DAEMON ===
        transfer_daemon = init_transfer_daemon(
            address=address,
            port=transfer_port(port)
        )

        # We don't have to listen to the transfer daemon
        # get and put services will do so

        # === PYRO DAEMON ===
        init_pyro_daemon(
            address=address,
            port=port
        )

        self.server_service = ServerService(
            sharings=sharings,
            name=name or socket.gethostname(),
            address=address,
            port=port,
            auth=auth,
            rexec=rexec
        )
        self.server_service.publish()

        log.i("PyroDaemon started at %s:%d",
              self.server_service.address(), self.server_service.port())
        log.i("TransferDaemon started at %s:%d",
              transfer_daemon.address(), transfer_daemon.port())

        if discover_daemon:
            log.i("DiscoverDaemon started at %s:%d",
                  discover_daemon.address(), discover_daemon.port())
        # else: disabled


    def start(self):
        """ Starts the the daemons """
        th_discover = threading.Thread(target=get_discover_daemon().run, daemon=True) \
            if get_discover_daemon() else None # discover can be disabled with discover_port = -1
        th_pyro = threading.Thread(target=get_pyro_daemon().requestLoop, daemon=True)
        th_transfer = threading.Thread(target=get_transfer_daemon().run, daemon=True)

        try:
            if th_discover:
                log.i("Starting DISCOVER daemon")
                th_discover.start()
            else:
                # Might be disabled for public server (for which discover won't work anyway)
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
            # Formally not a clean quit of the threads, but who cares we are exiting...

        log.i("FINISH")


    def server_info_full(self) -> ServerInfoFull:
        """
        Returns a 'ServerInfoFull' of this server
        (adds ip/port and discover info to 'ServerInfo'
        """

        si: ServerInfoFull = cast(ServerInfoFull, self.server_service.server_info())
        si["ip"] = self.server_service.address()
        si["port"] = self.server_service.port()

        si["discoverable"] = True if get_discover_daemon() else False

        if si["discoverable"]:
            si["discover_port"] = get_discover_daemon().port()

        return si

    def _handle_discover_request(self, client_endpoint: Endpoint, data: bytes):
        """ Callback invoked when a discover requests is received from the 'DiscoverDaemon' """
        log.i("<< DISCOVER %s", client_endpoint)
        log.i("Handling discover %s", str(data))


        response = create_success_response(self.server_info_full())

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            log.w("Invalid DISCOVER message received, ignoring it")
            return

        log.i("Client response port is %d", client_discover_response_port)

        # Respond to the port the client says in the paylod
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
