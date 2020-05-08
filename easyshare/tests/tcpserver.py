import time

from easyshare.consts.net import ADDR_ANY
from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.utils.types import bytes_to_str, str_to_bytes

s = SocketTcpAcceptor(ADDR_ANY, 5555)

while True:
    print("Waiting connections....")
    ns, endpoint = s.accept()
    print("Connection received from", endpoint)

    while True:
        inmsgraw = ns.recv()
        time.sleep(5)

        if not inmsgraw:
            print("Connection closed")
            break

        inmsg = bytes_to_str(inmsgraw)
        print("<< " + inmsg)

        if inmsg == "who":
            outmsg = __name__
            print(">> " + outmsg)
            ns.send(str_to_bytes(outmsg))
