from easyshare.utils.json import json_to_str, json_to_pretty_str
from easyshare.utils.ssl import parse_cert
import socket
import ssl
import tempfile

if __name__ == "__main__":


    dst = ('google.com', 443)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(dst)

    # upgrade the socket to SSL without checking the certificate
    # !!!! don't transfer any sensitive data over this socket !!!!
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(s, server_hostname=dst[0])

    # get certificate
    cert_bin = s.getpeercert(True)
    print(json_to_pretty_str(parse_cert(cert_bin)))
    # print("BINARY")
    # print(cert_bin)
    #
    # cert_str = ssl.DER_cert_to_PEM_cert(cert_bin)
    # print("ENCRYPTED")
    # print(cert_str)
    #
    # with tempfile.NamedTemporaryFile(mode="w") as tmpf:
    #     tmpf.write(cert_str)
    #     tmpf.flush()
    #
    #     decoded_cert = ssl._ssl._test_decode_cert(tmpf.name)
    #     print("DECRYPTED")
    #     print(json_to_pretty_str(decoded_cert))
