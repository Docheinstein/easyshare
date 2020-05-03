import ssl
from typing import Optional

import Pyro5
import Pyro5.socketutil

from easyshare.logging import get_logger

_ssl_context: Optional[ssl.SSLContext] = None

log = get_logger(__name__)


def get_ssl_context(*vargs, **kwargs) -> Optional[ssl.SSLContext]:
    log.d("get_ssl_context (%s)", "enabled" if _ssl_context else "disabled")
    return _ssl_context


def set_ssl_context(ssl_context: Optional[ssl.SSLContext]):
    global _ssl_context
    _ssl_context = ssl_context

    # Override pyro ssl context getter
    Pyro5.config.SSL = True if ssl_context else False
    Pyro5.socketutil.get_ssl_context = get_ssl_context

    log.i("SSL: %s", "enabled" if _ssl_context else "disabled")