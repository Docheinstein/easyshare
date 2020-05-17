import time

import Pyro4

from easyshare.tracing import enable_tracing
from easyshare.utils.net import get_primary_ip
from easyshare.utils.pyro import pyro_expose, pyro_client_endpoint

SUCCESS = {"success": True}
pyro_daemon = Pyro4.Daemon(host=get_primary_ip())


class PyroWorker:
    def __init__(self, owner, on_end):
        self.owner = owner
        self.on_end = on_end
        self.counter = 0

    @pyro_expose
    def work(self):
        resp = {"success": True, "data": "Work done for you ({})!".format(self.counter)}
        self.counter += 1
        return resp

    @pyro_expose
    def done(self):
        if self.on_end:
            self.on_end()

        return SUCCESS


class PyroServer:
    @pyro_expose
    def hello(self, *args):
        return SUCCESS


    @pyro_expose
    def block(self, t):
        time.sleep(int(t))

        return SUCCESS

    @pyro_expose
    def make(self, *args):
        def on_end():
            print("Unregistering worker")
            pyro_daemon.unregister(worker)

        worker = PyroWorker(pyro_client_endpoint(), on_end)
        worker_uri = str(pyro_daemon.register(worker))

        print("Worker URI: ", worker_uri)

        return {"success": True, "data": worker_uri}


if __name__ == "__main__":
    enable_tracing(True)

    pyro_server = PyroServer()
    uri = str(pyro_daemon.register(pyro_server))
    print("Server URI:", uri)

    with open("/tmp/server_uri.txt", mode="w") as f:
        f.write(uri)

    pyro_daemon.requestLoop()
