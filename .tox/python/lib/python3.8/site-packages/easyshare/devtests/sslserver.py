import ssl

from easyshare.sockets import SocketTcpAcceptor
from easyshare.utils.types import str_to_bytes, bytes_to_str

# Create cert and private key with:
# openssl req -x509 -keyout privkey.pem -days 365 -nodes -out cert.pem

# For read certificate content:
# openssl x509 -in cert.pem -text
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile="/home/stefano/Temp/certs/192_168_1_105/cert.pem",
                            keyfile="/home/stefano/Temp/certs/192_168_1_105/privkey.pem")
ssl_context.verify_mode = ssl.CERT_NONE

host = "192.168.1.105"
port = 5555

def main():
    s = SocketTcpAcceptor(address=host, port=port)

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