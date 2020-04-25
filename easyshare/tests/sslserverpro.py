import ssl

from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.utils.net import create_server_ssl_context
from easyshare.utils.types import bytes_to_str


host = "localhost"
port = 6666


def main():
    s = SocketTcpAcceptor(address=host,
                          port=port,
                          ssl_context=create_server_ssl_context(
                              cert="/home/stefano/Temp/certs/localhost/cert.pem",
                              privkey="/home/stefano/Temp/certs/localhost/privkey.pem"
                          ))

    while True:
        print("Waiting secure connections....")
        ns, endpoint = s.accept()
        print("Connection received from", endpoint)
        while True:
            inraw = ns.recv(1024)
            print("<< " + bytes_to_str(inraw))


if __name__ == "__main__":
    main()