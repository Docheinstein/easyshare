from typing import Optional, Callable

from easyshare.endpoint import Endpoint
from easyshare.esd.daemons import TcpDaemon
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# =============================================
# ================= API DAEMON ================
# =============================================


_api_daemon: Optional['ApiDaemon'] = None


class ApiDaemon(TcpDaemon):
    pass

def init_api_daemon(address: str, port: int) -> ApiDaemon:
    global _api_daemon
    _api_daemon = ApiDaemon(address, port)
    return _api_daemon


def get_api_daemon() -> Optional[ApiDaemon]:
    return _api_daemon