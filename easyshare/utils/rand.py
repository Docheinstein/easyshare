import random
import string
from uuid import uuid4


def randstring(length: int = 16, alphabet: str  = string.ascii_letters + string.digits) -> str:
    return "".join([random.choice(alphabet) for _ in range(length)])


def uuid() -> str:
    return uuid4().hex
