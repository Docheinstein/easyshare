import hashlib
import os
from base64 import b64encode, b64decode
from typing import Union, Optional, Tuple

from easyshare.utils.types import to_bytes, bytes_to_str, str_to_bytes


def scrypt(plain: Union[str, bytes], salt: Union[str, bytes] = None,
           n: int = 2048, r: int = 8, p: int = 1, dklen: int = 64) -> Optional[bytes]:
    plain_b = to_bytes(plain)
    salt_b = to_bytes(salt)

    if not plain_b or not salt_b:
        return None

    # print("scrypt plain: ", plain)
    # print("scrypt plain_b: ", plain_b)
    # print("scrypt salt: ", salt)
    # print("scrypt salt_b: ", salt_b)

    hashed_b = hashlib.scrypt(
        password=plain_b,
        salt=salt_b,
        n=n,
        r=r,
        p=p,
        dklen=dklen
    )

    return hashed_b


def scrypt_new(plain: Union[str, bytes], salt_length: int = 32,
               n: int = 2048, r: int = 8, p: int = 1, dklen: int = 64) -> Tuple[bytes, bytes]:
    salt_b = os.urandom(salt_length)
    return salt_b, scrypt(plain, salt_b, n, r, p, dklen)


def str_to_b64(s: str) -> str:
    return bytes_to_b64(str_to_bytes(s))


def bytes_to_b64(b: bytes) -> str:
    return str(b64encode(b), encoding="ASCII")


def b64_to_bytes(s: str) -> bytes:
    return b64decode(s)
