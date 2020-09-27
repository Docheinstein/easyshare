import ssl
from typing import Optional, Dict, Callable

from easyshare.logging import get_logger
from easyshare.endpoint import Endpoint
from easyshare.sockets import SocketTcpOut
from easyshare.utils.ssl import parse_ssl_certificate, SSLCertificate, create_client_ssl_context

log = get_logger(__name__)

# Global SSL context
# If None, then SSL is disabled
_ssl_context: Optional[ssl.SSLContext] = None

# Parsed certificates cache
_ssl_certs_cache: Dict[Endpoint, dict] = {}


def get_ssl_context() -> Optional[ssl.SSLContext]:
    """ Get the global SSLContext """
    log.d("get_ssl_context (%s)", "enabled" if _ssl_context else "disabled")
    return _ssl_context


def set_ssl_context(ssl_context: Optional[ssl.SSLContext]):
    """ Set the global SSLContext """

    global _ssl_context
    _ssl_context = ssl_context

    log.i("SSL: %s", "enabled" if _ssl_context else "disabled")


def get_cached_or_parse_ssl_certificate(
        endpoint: Endpoint,
        peercert_provider: Callable[..., Optional[bytes]]) -> Optional[SSLCertificate]:
    """
    Returns the cached 'SSLCertificate' for the given 'endpoint' or parses the
    one provided by 'peercert_provider' then parses and caches it.
    """

    if endpoint not in _ssl_certs_cache:
        log.d("No cached SSL cert found for %s, fetching and parsing now", endpoint)
        cert_bin = peercert_provider()
        cert = None
        try:
            cert = parse_ssl_certificate(cert_bin)
        except:
            log.eexception("Certificate parsing error occurred")
        _ssl_certs_cache[endpoint] = cert
    else:
        log.d("Found cached SSL cert for %s", endpoint)

    return _ssl_certs_cache[endpoint]


def get_cached_or_fetch_ssl_certificate_for_endpoint(endpoint: Endpoint) -> Optional[SSLCertificate]:
    """
    Returns the cached 'SSLCertificate' for the given 'endpoint' or fetches it
    from the remote socket (a network op. is involved), then parses and caches it.
    """
    return get_cached_or_parse_ssl_certificate(
        endpoint=endpoint,
        peercert_provider=lambda: SocketTcpOut(
            endpoint[0], endpoint[1],
            ssl_context=create_client_ssl_context()
        ).ssl_certificate()
    )
