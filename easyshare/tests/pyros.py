import time

import Pyro4

from easyshare.server.common import trace_pyro_api
from easyshare.utils.net import get_primary_ip


class PyroServer:
    @Pyro4.expose
    @trace_pyro_api
    def hello(self, *args):
        print("hello() (", Pyro4.current_context.client_sock_addr, ")")
        return {
            "success": True
        }


    @Pyro4.expose
    @trace_pyro_api
    def block(self, t):
        print("block() {} (".format(int(t)), Pyro4.current_context.client_sock_addr, ")")
        time.sleep(int(t))
        print("block() END (", Pyro4.current_context.client_sock_addr, ")")

        return {
            "success": True
        }


if __name__ == "__main__":
    pyro_server = PyroServer()
    pyro_daemon = Pyro4.Daemon(host=get_primary_ip())
    uri = pyro_daemon.register(pyro_server).asString()
    print("Server URI:", uri)

    with open("/tmp/server_uri.txt", mode="w") as f:
        f.write(uri)

    pyro_daemon.requestLoop()
