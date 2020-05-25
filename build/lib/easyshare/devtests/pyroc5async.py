import concurrent
import threading
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Union

from Pyro5.api import Proxy

from easyshare.devtests.pyros import PyroServer
from easyshare.tracing import enable_tracing
from easyshare.utils.pyro import TracedPyroProxy



#
# def run_cmd(comm):
#     global worker
#
#     if comm.startswith(":"):
#         resp = pyro_server.__getattr__(comm[1:])()
#         return
#
#     with ThreadPoolExecutor() as pool:
#         print("Inside the pool")
#
#         def receiver():
#             print("Receiver started...")
#             resp = pyro_server.recv()
#             print("Receiver finished...")
#             return resp
#
#         def sender():
#             print("Sender started...")
#             resp = pyro_server.send()
#             print("Sender finished...")
#             return resp
#
#         recv_future = pool.submit(receiver)
#         send_future = pool.submit(sender)
#
#         recv_future.add_done_callback(lambda _: print("recv done"))
#         send_future.add_done_callback(lambda _: print("send done"))
#
#         for future in concurrent.futures.as_completed([recv_future, send_future]):
#
#         recv_res = recv_future.result()
#         send_res = send_future.result()
#
#         print("recv_res", recv_res)
#         print("send_res", send_res)

if __name__ == "__main__":
    enable_tracing(True)

    with open("/tmp/pyro5async.uri", mode="r") as f:
        uri = f.read()

    print("Initializing proxy at URI:", uri)
    pyro_server = TracedPyroProxy(uri)
    print("Initialized proxy")

    finished = False

    def receiver():
        pyro_server_receiver = TracedPyroProxy(uri)
        while not finished:
            pyro_server_receiver.recv()


    th = threading.Thread(target=receiver)
    th.start()

    for i in range(10):
        pyro_server.send()

    finished = True

    th.join()