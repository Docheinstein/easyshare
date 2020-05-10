import ssl

from easyshare.es.ui import ssl_certificate_to_pretty_str
from easyshare.sockets import SocketTcpOut
from easyshare.utils.ssl import create_client_ssl_context, parse_ssl_certificate
from easyshare.utils.types import str_to_bytes

host = "localhost"
port = 6666


def main():
    s = SocketTcpOut(host, port, ssl_context=create_client_ssl_context())
    print("Connected")

    print("SSL sock version:", s.sock.version())
    print("Peer name:", s.remote_address())
    print("Peer cert:")
    print(ssl_certificate_to_pretty_str(parse_ssl_certificate(s.ssl_certificate())))

    while True:
        msg = input("$ ")
        s.send(str_to_bytes(msg))


if __name__ == "__main__":
    main()
