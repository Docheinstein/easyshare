from typing import Optional, Callable

from easyshare.endpoint import Endpoint
from easyshare.esd.daemons import Daemon, UdpDaemon
from easyshare.logging import get_logger
from easyshare.sockets import SocketUdpIn
from easyshare.tracing import trace_in
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)


# =============================================
# ============== DISCOVER DAEMON ==============
# =============================================


_discover_daemon: Optional['DiscoverDaemon'] = None


class DiscoverDaemon(UdpDaemon):
    """
    Daemon that listens to discover requests from the client (by default on port 12019)
    and notifies the listeners about it.
    """

    def _trace_hook(self, data: bytes, client_endpoint: Endpoint):
        trace_in(
            "DISCOVER {} ({})".format(str(data), bytes_to_int(data)),
            ip=client_endpoint[0],
            port=client_endpoint[1]
        )


def init_discover_daemon(port: int) -> DiscoverDaemon:
    """ Initializes the global discover daemon on the given port """
    global _discover_daemon
    _discover_daemon = DiscoverDaemon(port)
    return _discover_daemon


def get_discover_daemon() -> Optional[DiscoverDaemon]:
    """ Get the global discover daemon instance """
    return _discover_daemon