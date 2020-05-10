import random
import threading
import time

from easyshare.colors import red

SLEEP_FACTOR = 0

class Counter:
    def __init__(self):
        self.value = 0

    def advance(self) -> int:
        x = self.value
        self.value += 1
        return x

sem = threading.Semaphore(0)
lock = threading.RLock()

buffer = []


c = Counter()

stop = False

concurrent_accesses = Counter()


def pusher():
    global concurrent_accesses
    global c

    can_exit = False

    while not can_exit:
        print("[++++] LOCK acquire")
        lock.acquire()
        print("[++++] LOCK acquire | END")
        assert concurrent_accesses.value == 0
        concurrent_accesses.value += 1

        # ----------

        if stop is True:
            print("[++++] END of pusher")
            buffer.append(None)
            can_exit = True
        else:
            cnt = random.randint(1, 4)
            for j in range(cnt):
                val = c.advance()
                time.sleep(random.random() * SLEEP_FACTOR)
                print("[++++] PUSH {} ({}/{})".format(val, j + 1, cnt))
                buffer.append(val)

        # ----------

        concurrent_accesses.value -= 1
        assert concurrent_accesses.value == 0

        print("[++++] SEM post")
        sem.release()
        print("[++++] SEM post | END")

        # time.sleep(random.random()

        assert concurrent_accesses.value == 0

        print("[++++] LOCK release")
        lock.release()
        print("[++++] LOCK release | END")

        print("[++++] SLEEP")
        time.sleep(random.random() * 3 * SLEEP_FACTOR)
        print("[++++] SLEEP | END")

    print("[++++] QUIT")


def puller():
    global concurrent_accesses
    global c

    can_exit = False

    while not can_exit:
        print(red("[----] SEM wait"))
        sem.acquire()
        print(red("[----] SEM wait | END"))

        # ---------

        print(red("[----] LOCK acquire"))
        lock.acquire()
        print(red("[----] LOCK acquire | END"))
        assert concurrent_accesses.value == 0
        concurrent_accesses.value += 1

        reads = []
        while buffer:
            val = buffer.pop(0)
            print(red("[----] PULL {}".format(val)))
            reads.append(val)

        # --------

        concurrent_accesses.value -= 1
        assert concurrent_accesses.value == 0

        print(red("[++++] LOCK release"))
        lock.release()
        print(red("[++++] LOCK release | END"))

        for v in reads:
            if v is None:
                print(red("[----] END of puller"))
                can_exit = True
            else:
                print(red("< {}".format(v)))

    print(red("[----] QUIT"))


if __name__ == "__main__":
    t1 = threading.Thread(target=pusher)
    t2 = threading.Thread(target=puller)
    t1.start()
    t2.start()

    input()
    stop = True

    t1.join()
    t2.join()
