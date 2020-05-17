import os
import socket
import ssl
import tempfile
from typing import Dict, Optional, Union

from easyshare.logging import get_logger

log = get_logger(__name__)

try:
    # From python 3.8
    from typing import TypedDict

    class SSLCertificatePart(TypedDict):
        country: str
        state: str
        locality: str
        organization: str
        organization_unit: str
        common_name: str
        email: str


    class SSLCertificate(TypedDict):
        subject: SSLCertificatePart
        issuer: SSLCertificatePart

        valid_from: str
        valid_to: str
        serial: str
        self_signed: bool


except:
    SSLCertificatePart = Dict[str, str]
    SSLCertificate = Dict[str, Union[SSLCertificatePart], str, bool]



def create_server_ssl_context(cert: str, privkey: str) -> Optional[ssl.SSLContext]:
    """ Create a server ssl.SSLContext from the given certificate an private key paths """
    if not os.path.isfile(cert) or not os.path.isfile(privkey):
        return None

    try:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=cert, keyfile=privkey)
        ssl_context.verify_mode = ssl.CERT_NONE
    except Exception as ex:
        log.e("SSL context creation failed: %s", ex)
        return None

    return ssl_context


def create_client_ssl_context() -> Optional[ssl.SSLContext]:
    """ Create a client ssl.SSLContext (trust-all) """
    try:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    except Exception as ex:
        log.e("SSL context creation failed: %s", ex)
        return None

    return ssl_context


def sslify_socket(sock: socket.socket, ssl_context: ssl.SSLContext,
                  server_side: bool = False, server_hostname: str = None) -> ssl.SSLSocket:
    """ Wraps the socket creating an ssl.SSLSocket for client or server side """
    ssock = sock
    if ssl_context:
        if server_side:
            ssock = ssl_context.wrap_socket(sock, server_side=server_side)
        elif server_hostname:
            ssock = ssl_context.wrap_socket(sock, server_hostname=server_hostname)
        else:
            ssock = ssl_context.wrap_socket(sock)
    return ssock


def parse_ssl_certificate(cert_der: bytes) -> Optional[SSLCertificate]:
    """
    Takes dict certificate as given by_test_decode_cert and parse
    it to an'SSLCertificate'
    """

    d = _parse_ssl_certificate_der(cert_der)
    if not d:
        return None

    cert = {}

    def parse_part(part_list: list, part_dict: dict):
        for field in part_list:
            for subfield in field:
                if len(subfield) == 2:
                    subfield_k, subfield_v = subfield[0], subfield[1]
                    if subfield_k in _SSL_CERT_PARSING_MAP:
                        part_dict[_SSL_CERT_PARSING_MAP[subfield_k]] = subfield_v

    # print("Parsing", j(d))

    for rootfield_k, rootfield_v in d.items():
        if rootfield_k == "subject" or rootfield_k == "issuer":
            cert[rootfield_k] = {}
            parse_part(rootfield_v, cert[rootfield_k])
        elif rootfield_k in _SSL_CERT_PARSING_MAP:
            cert[_SSL_CERT_PARSING_MAP[rootfield_k]] = rootfield_v

    # Check whether is self signed (issuer its the same as the subject)
    self_signed = (cert.get("subject", 1) == cert.get("issuer", 2))

    cert["self_signed"] = self_signed

    return cert


def _parse_ssl_certificate_der(cert_der: bytes) -> Optional[Dict]:
    """ Parse a certificate in binary form """
    cert_pem = ssl.DER_cert_to_PEM_cert(cert_der)
    return _parse_ssl_certificate_pem(cert_pem)


def _parse_ssl_certificate_pem(cert_pem: str) -> Optional[Dict]:
    """ Parse a certificate in string form """
    # Uses '_test_decode_cert', an internal API of cpython
    # which takes a file as an input, so we have to create a temporary file
    # and fill it with the pem content
    with tempfile.NamedTemporaryFile(mode="w") as tmpf:
        tmpf.write(cert_pem)
        tmpf.flush()
        # noinspection PyProtectedMember
        # noinspection PyUnresolvedReferences
        cert_info = ssl._ssl._test_decode_cert(tmpf.name)
        return cert_info


# Map python's SSL certificate fields to our SSLCertificate fields
_SSL_CERT_PARSING_MAP = {
    "serialNumber": "serial",
    "notBefore": "valid_from",
    "notAfter": "valid_to",

    "countryName": "country",
    "stateOrProvinceName": "state",
    "localityName": "locality",
    "organizationName": "organization",
    "organizationalUnitName": "organization_unit",
    "commonName": "common_name",
    "emailAddress": "email",
}
