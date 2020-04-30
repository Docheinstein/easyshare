from easyshare.socket.tcp import SocketTcpOut
from easyshare.utils.json import json_to_str
import socket
import ssl

from easyshare.utils.ssl import parse_cert_der, create_client_ssl_context

if __name__ == "__main__":
    d1 = SocketTcpOut(
        address="google.com", port=443, ssl_context=create_client_ssl_context()
    ).ssl_certificate()
    c1 = parse_cert_der(d1)
    print(json_to_str(c1))

    # ----------

    dst = ('google.com', 443)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(dst)

    # upgrade the socket to SSL without checking the certificate
    # !!!! don't transfer any sensitive data over this socket !!!!
    ssl_context = ssl.create_default_context()
    # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    s = ssl_context.wrap_socket(s, server_hostname=dst[0])

    # get certificate
    d2 = s.getpeercert(True)
    c2 = parse_cert_der(d2)
    print(json_to_str(c2))

    assert c1 == c2

    print("OK: same cert")
