import os
import sys
import threading
import time


class SomeThread(threading.Thread):

    def run(self) -> None:
        print("RUNNING")

        while True:
            time.sleep(1)
            print("STILL RUNNING")

    def acall(self):
        print("ACALL")

if __name__ == "__main__":
    t = SomeThread()
    t.start()
    while True:
        t.acall()
        time.sleep(0.5)