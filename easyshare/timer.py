import time
from enum import Enum
from typing import List, Tuple

class Timer:
    class Event(Enum):
        START = 0
        STOP = 1

    def __init__(self, start: bool = True):
        self._events:List[Tuple[Timer.Event, int]] = []
        if start:
            self.start()

    def elapsed(self) -> int:
        # Compute the elapsed time by summing the delta between consecutive
        # Event.START and Event.STOP
        deltas_sum = 0
        i = 0
        while i < len(self._events):
            ev_start, t_start = self._events[i]
            if ev_start == Timer.Event.START:
                i += 1
                while i < len(self._events):
                    ev_stop, t_stop = self._events[i]
                    if ev_stop == Timer.Event.STOP:
                        deltas_sum += t_stop - t_start
                        break
                    i += 1
            i += 1

        return deltas_sum

    def elapsed_ns(self):
        return self.elapsed()

    def elapsed_ms(self):
        return self.elapsed() * 1e-6

    def elapsed_s(self):
        return self.elapsed() * 1e-9

    def start(self):
        self._events.append((Timer.Event.START, time.monotonic_ns()))

    def stop(self) -> int:
        self._events.append((Timer.Event.STOP, time.monotonic_ns()))
        return self.elapsed()

    def resume(self):
        self._events.append((Timer.Event.START, time.monotonic_ns()))

    def pause(self):
        self._events.append((Timer.Event.STOP, time.monotonic_ns()))

    def __str__(self):
        s = ""
        for ev, t in self._events:
            s += str(ev) + ": " + str(t) + "\n"
        return s

if __name__ == "__main__":
    t = Timer(start=True)
    time.sleep(2)
    t.start()
    time.sleep(0.5)
    t.resume()
    time.sleep(0.2)
    t.stop()
    time.sleep(1)
    print(t.stop() *  1e-9, "s")
    print(t)
