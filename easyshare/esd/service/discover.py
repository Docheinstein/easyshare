from easyshare.endpoint import Endpoint
from easyshare.esd.daemons.discover import get_discover_daemon
from easyshare.logging import get_logger
from easyshare.protocol.responses import create_success_response
from easyshare.protocol.types import ServerInfoFull
from easyshare.sockets import SocketUdpOut
from easyshare.tracing import trace_out
from easyshare.utils.json import json_to_bytes
from easyshare.utils.net import is_valid_port
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)

class DiscoverService:
    def __init__(self, server_info_full: ServerInfoFull):
        self._server_info_full = server_info_full
        get_discover_daemon().add_callback(self._handle_discover_request)


    def _handle_discover_request(self, client_endpoint: Endpoint, data: bytes) -> bool:
        """ Callback invoked when a discover requests is received from the 'DiscoverDaemon' """
        log.i("<< DISCOVER %s", client_endpoint)
        log.i("Handling discover %s", str(data))

        response = create_success_response(self._server_info_full)

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            log.w("Invalid DISCOVER message received, ignoring it")
            return False # not handled

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

        return True # handled