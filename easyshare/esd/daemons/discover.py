from typing import Optional

from easyshare.common import TransferDirection, TransferProtocol
from easyshare.endpoint import Endpoint
from easyshare.esd.daemons import UdpDaemon
from easyshare.logging import get_logger
from easyshare.tracing import get_tracing_level, TRACING_TEXT, trace_text
from easyshare.utils.types import btoi

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

    def _trace_hook(self, data: bytes, endpoint: Endpoint):
        if get_tracing_level() == TRACING_TEXT: # check for avoid json_pretty_str call
            trace_text(
                str(btoi(data)),
                sender=endpoint, receiver=self._sock.endpoint(),
                direction=TransferDirection.IN, protocol=TransferProtocol.UDP
            )


def init_discover_daemon(port: int) -> DiscoverDaemon:
    """ Initializes the global discover daemon on the given port """
    global _discover_daemon
    _discover_daemon = DiscoverDaemon(port, trace=get_tracing_level() > TRACING_TEXT)
    return _discover_daemon


def get_discover_daemon() -> Optional[DiscoverDaemon]:
    """ Get the global discover daemon instance """
    return _discover_daemon