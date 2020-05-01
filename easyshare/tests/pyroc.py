import threading
from typing import Union

import Pyro4

from easyshare.tests.pyros import PyroServer
from easyshare.utils.json import json_to_pretty_str


if __name__ == "__main__":
    with open("/tmp/server_uri.txt", mode="r") as f:
        uri = f.read()

    print("Initializing proxy at URI:", uri)
    pyro_server: Union[Pyro4.Proxy, PyroServer] = Pyro4.Proxy(uri)
    print("Initialized proxy")

    def run_cmd(cmd_parts):
        print(cmd_parts)
        resp = pyro_server.__getattr__(cmd_parts[0])(*cmd_parts[1:])
        print(json_to_pretty_str(resp))


    while True:
        command = input("$ ")
        if command == "q":
            break
        if command.startswith(":"):
            command = command[1:]
            command_parts = command.split(" ")
            threading.Thread(target=run_cmd, args=command_parts).start()
        else:
            command_parts = command.split(" ")
            run_cmd(command_parts)
