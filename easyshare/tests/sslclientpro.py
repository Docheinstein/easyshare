import ssl

from easyshare.socket.tcp import SocketTcpOut
from easyshare.utils.net import create_client_ssl_context
from easyshare.utils.types import  str_to_bytes

host = "localhost"
port = 6666


def main():
    s = SocketTcpOut(host, port,
                     ssl_context=create_client_ssl_context()
                     )
    print("Connected")

    print("SSL sock version:", s.sock.version())
    print("Peer name:", s.sock.getpeername())
    print("Peer cert:", s.sock.getpeercert())

    while True:
        msg = input("$ ")
        s.send(str_to_bytes(msg))


if __name__ == "__main__":
    main()
