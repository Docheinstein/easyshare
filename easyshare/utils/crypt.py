import hashlib
import os
from base64 import b64encode, b64decode
from typing import Union, Optional, Tuple

from easyshare.utils.types import to_bytes, stob, is_bytes


b64 = str


def scrypt(plain: Union[str, bytes], salt: Union[b64, bytes],
           n: int = 2048, r: int = 8, p: int = 1, dklen: int = 64) -> Optional[bytes]:
    """ Create the scrypt hash of the given plaintext, salt """

    plain_b = to_bytes(plain)
    salt_b = salt if is_bytes(salt) else b64_to_bytes(salt)

    if not plain_b or not salt_b:
        raise ValueError("scrypt failed: 'plain' and 'salt' must be specified")

    # print("scrypt plain: ", plain)
    # print("scrypt plain_b: ", plain_b)
    # print("scrypt salt: ", salt)
    # print("scrypt salt_b: ", salt_b)

    hash_b = hashlib.scrypt(
        password=plain_b,
        salt=salt_b,
        n=n,
        r=r,
        p=p,
        dklen=dklen
    )

    return hash_b


def scrypt_new(plain: Union[str, bytes], salt_length: int = 32,
               n: int = 2048, r: int = 8, p: int = 1, dklen: int = 64) -> Tuple[bytes, bytes]:
    """ Create a scrypt hash of the given plaintext, generating a salt of the given length """
    salt_b = os.urandom(salt_length)
    hash_b = scrypt(plain, salt_b, n, r, p, dklen)
    return salt_b, hash_b


def str_to_b64(s: str) -> b64:
    return bytes_to_b64(stob(s))


def bytes_to_b64(b: bytes) -> b64:
    return str(b64encode(b), encoding="ASCII")


def b64_to_bytes(s: b64) -> bytes:
    return b64decode(s)