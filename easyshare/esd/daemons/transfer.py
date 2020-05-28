from typing import Optional, Callable

from easyshare.endpoint import Endpoint
from easyshare.esd.daemons import TcpDaemon
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# =============================================
# ============== TRANSFER DAEMON ==============
# =============================================


_transfer_daemon: Optional['TransferDaemon'] = None


class TransferDaemon(TcpDaemon):
    """
    Transfer daemon that listens to new requests from clients (by default on port 12021)
    add notifies the listeners about the incoming connections.
    The sense is that the listeners of this daemon (a 'TransferService', e.g. get or put)
    should handle the new socket (after some check, e.g. IP provenience).
    """

def init_transfer_daemon(address: str, port: int) -> TransferDaemon:
    """ Initializes the global transfer daemon on the given port """
    global _transfer_daemon
    _transfer_daemon = TransferDaemon(address, port)
    return _transfer_daemon


def get_transfer_daemon() -> Optional[TransferDaemon]:
    """ Get the global transfer daemon instance """
    return _transfer_daemon