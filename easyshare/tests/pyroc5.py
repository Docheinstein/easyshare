import threading
from typing import Union

from Pyro5.api import Proxy

from easyshare.tests.pyros import PyroServer
from easyshare.tracing import enable_tracing
from easyshare.utils.pyro import TracedPyroProxy

worker = None


def run_cmd(cmd_parts, claim_ownership):
    global worker

    if claim_ownership:
        pyro_server._pyroClaimOwnership()
    print(cmd_parts)
    comm_name = cmd_parts[0]
    comm_args = cmd_parts[1:]
    if comm_name == "work" or comm_name == "done" and worker:
        worker.__getattr__(comm_name)()
    else:
        resp = pyro_server.__getattr__(comm_name)(*comm_args)

        if comm_name == "make":
            worker_uri = resp.get("data")
            worker = TracedPyroProxy(worker_uri)
            print("Initialized worker at URI:", worker_uri)



if __name__ == "__main__":
    enable_tracing(True)

    with open("/tmp/server_uri.txt", mode="r") as f:
        uri = f.read()

    print("Initializing proxy at URI:", uri)
    pyro_server: Union[Proxy, PyroServer] = TracedPyroProxy(uri)
    print("Initialized proxy")


    while True:
        command = input("$ ")
        if command == "q":
            break
        if command.startswith(":"):
            command = command[1:]
            command_parts = command.split(" ")
            print("command:",command)
            print("command_parts:",command_parts)
            threading.Thread(target=run_cmd, args=(command_parts, False)).start()
        else:
            command_parts = command.split(" ")
            run_cmd(command_parts, False)
