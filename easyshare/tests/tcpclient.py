from easyshare.socket import SocketTcpOut
from easyshare.utils.net import get_primary_ip
from easyshare.utils.types import str_to_bytes, bytes_to_str

s = SocketTcpOut(get_primary_ip(), 5555)
print("Connected")

while True:
    outmsg = input(">> ")

    if outmsg == "recv":
        inmsgraw = s.recv()
        inmsg = bytes_to_str(inmsgraw)
        print("<< " + inmsg)

    s.send(str_to_bytes(outmsg))
