from easyshare.socket.udp import SocketUdpOut
from easyshare.utils.net import get_primary_ip
from easyshare.utils.types import str_to_bytes, bytes_to_str

TO = (get_primary_ip(), 6666)
s = SocketUdpOut()

while True:
    outmsg = input(">> ")

    if outmsg == "recv":
        inmsgraw, endpoint = s.recv()
        inmsg = bytes_to_str(inmsgraw)
        print("<< {} {}".format(inmsg, endpoint))

    s.send(str_to_bytes(outmsg), TO[0], TO[1])
