import time
from datetime import datetime

_HUMAN_TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M:%S"

def ns() -> int:
    return time.time_ns()

def ms() -> int:
    return int(ns() * 1e-6)

def timestamp() -> str:
    return datetime.now().strftime(_HUMAN_TIMESTAMP_FORMAT)

def ns2timestamp(nanos: int) -> str:
    return datetime.fromtimestamp(nanos * 1e-9).strftime(_HUMAN_TIMESTAMP_FORMAT)

def ms2timestamp(millis: int) -> str:
    return datetime.fromtimestamp(millis * 1e-3).strftime(_HUMAN_TIMESTAMP_FORMAT)