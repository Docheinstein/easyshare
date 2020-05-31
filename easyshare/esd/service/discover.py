from easyshare.common import TransferDirection, TransferProtocol
from easyshare.endpoint import Endpoint
from easyshare.esd.daemons.discover import get_discover_daemon
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfoFull
from easyshare.sockets import SocketUdpOut
from easyshare.tracing import TRACING_TEXT, get_tracing_level, trace_text
from easyshare.utils.json import jtob, j
from easyshare.utils.net import is_valid_port
from easyshare.utils.types import btoi

log = get_logger(__name__)

class DiscoverService:
    def __init__(self, server_info_full: ServerInfoFull):
        self._server_info_full = server_info_full
        get_discover_daemon().add_callback(self._handle_discover_request)


    def _handle_discover_request(self, client_endpoint: Endpoint, data: bytes) -> bool:
        """ Callback invoked when a discover requests is received from the 'DiscoverDaemon' """
        log.i("<< DISCOVER %s", client_endpoint)
        log.i("Handling discover %s", str(data))

        response = self._server_info_full

        log.d("Will send response %s", response)

        client_discover_response_port = btoi(data)

        if not is_valid_port(client_discover_response_port):
            log.w("Invalid DISCOVER message received, ignoring it")
            return False # not handled

        log.i("Client response port is %d", client_discover_response_port)

        # Respond to the port the client says in the paylod
        # (not necessary the one from which the request come)
        sock = SocketUdpOut()

        log.d("Sending DISCOVER response back to %s:%d",
              client_endpoint[0], client_discover_response_port)

        if get_tracing_level() == TRACING_TEXT: # check for avoid json_pretty_str call
            trace_text(
                j(response),
                sender=sock.endpoint(), receiver=(client_endpoint[0], client_discover_response_port),
                direction=TransferDirection.OUT, protocol=TransferProtocol.UDP
            )

        sock.send(jtob(response), client_endpoint[0], client_discover_response_port)

        return True # handled