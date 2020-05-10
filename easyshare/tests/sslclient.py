import ssl

from easyshare.sockets import SocketTcpOut


from easyshare.utils.types import  str_to_bytes

host = "192.168.1.105"
port = 5555

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
# ssl_context.load_verify_locations("/home/stefano/Temp/certs/localhost/cert.pem")

ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def main():
    s = SocketTcpOut(host, port)
    print("Connected")
    with ssl_context.wrap_socket(s.sock) as sslsock:
        print("SSL sock version:", sslsock.version())
        print("Peer name:", sslsock.getpeername())
        print("Peer cert:", sslsock.getpeercert())
        while True:
            msg = input("$ ")
            sslsock.send(str_to_bytes(msg))


if __name__ == "__main__":
    main()
