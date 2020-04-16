import ssl

from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.utils.types import str_to_bytes, bytes_to_str

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile="/home/stefano/Temp/certs/localhost/cert.pem",
                            keyfile="/home/stefano/Temp/certs/localhost/private_key.pem")
ssl_context.verify_mode = ssl.CERT_NONE

def main():
    s = SocketTcpAcceptor(port=5555)

    while True:
        with ssl_context.wrap_socket(s.sock, server_side=True) as sslsock:
            print("Waiting secure connections....")
            ns, endpoint = sslsock.accept()
            print("Connection received from", endpoint)
            while True:
                inraw = ns.recv(1024)
                print("<< " + bytes_to_str(inraw))

if __name__ == "__main__":
    main()