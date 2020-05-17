import time

from Pyro5.api import Daemon, expose

from easyshare.tracing import enable_tracing
from easyshare.utils.net import get_primary_ip
from easyshare.utils.pyro import pyro_client_endpoint, trace_api

SUCCESS = {"success": True}
pyro_daemon = Daemon(host=get_primary_ip())


class PyroTask:
    @expose
    @trace_api
    def recv(self):
        print("Recv...")
        time.sleep(5)
        print("Recv OK")
        return SUCCESS


    @expose
    @trace_api
    def send(self):
        print("Send...")
        time.sleep(1.5)
        print("Send OK")
        return SUCCESS


if __name__ == "__main__":
    enable_tracing(True)

    pyro_task = PyroTask()
    uri = str(pyro_daemon.register(pyro_task))
    print("Server URI:", uri)

    with open("/tmp/pyro5async.uri", mode="w") as f:
        f.write(uri)

    pyro_daemon.requestLoop()
