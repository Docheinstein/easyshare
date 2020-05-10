from easyshare.sockets import SocketUdpIn
from easyshare.utils.types import bytes_to_str, str_to_bytes

s = SocketUdpIn(port=6666)

while True:
    print("Waiting messages....")

    inmsgraw, endpoint = s.recv()

    if not inmsgraw:
        print("Nothing received")
        continue

    inmsg = bytes_to_str(inmsgraw)
    print("<< {} {}".format(inmsg, endpoint))

    if inmsg == "who":
        outmsg = __name__
        print(">> " + outmsg)
        s.send(str_to_bytes(outmsg), endpoint[0], endpoint[1])
