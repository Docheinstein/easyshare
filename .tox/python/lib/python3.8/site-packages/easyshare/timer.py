import time
from enum import Enum
from typing import List, Tuple

class Timer:
    """
    Basic timer which can be started and stopped as needed
    and is able to compute the elapsed delta while being
    aware of the interruptions.
    """
    class Event(Enum):
        START = 0
        STOP = 1

    def __init__(self, start: bool = True):
        self._events:List[Tuple[Timer.Event, int]] = []
        if start:
            self.start()

    def elapsed(self) -> int: # ns
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
        # Actually is start(), but with a more reasonable name
        self._events.append((Timer.Event.START, time.monotonic_ns()))

    def pause(self):
        # Actually is stop(), but with a more reasonable name
        self._events.append((Timer.Event.STOP, time.monotonic_ns()))

    def __str__(self):
        s = ""
        for ev, ev_t in self._events:
            s += str(ev) + ": " + str(ev_t) + "\n"
        return s