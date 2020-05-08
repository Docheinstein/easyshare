import threading
import time

from easyshare.consts.net import ADDR_ANY
from easyshare.socket.tcp import SocketTcpAcceptor, SocketTcpIn
from easyshare.utils.types import bytes_to_str, str_to_bytes

s = SocketTcpAcceptor(ADDR_ANY, 5555)

def talk(sock: SocketTcpIn):
    print("Connection received from", sock.remote_endpoint())
    print("Server sock: ", sock.endpoint())
    while True:
        inmsgraw = sock.recv()

        if not inmsgraw:
            print("Connection closed (%s)", endpoint)
            break

        inmsg = bytes_to_str(inmsgraw)
        print("<< " + inmsg)

        if inmsg == "who":
            outmsg = __name__
            print(">> " + outmsg)
            ns.send(str_to_bytes(outmsg))


while True:
    print("Waiting connections....")
    while True:

        ns, endpoint = s.accept()
        threading.Thread(target=talk, args=(ns, ), daemon=True).start()
