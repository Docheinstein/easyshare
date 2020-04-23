from abc import ABC, abstractmethod
from typing import Optional

from easyshare.utils.crypt import scrypt_new, bytes_to_b64, scrypt, b64


class Auth(ABC):

    @abstractmethod
    def match(self, password: Optional[str]) -> bool:
        pass

    @classmethod
    @abstractmethod
    def algo_security(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def algo_name(cls) -> str:
        pass


class AuthNone(Auth):
    def match(self, password: Optional[str]) -> bool:
        return True

    @classmethod
    def algo_security(cls) -> int:
        return 0

    @classmethod
    def algo_name(cls) -> str:
        return "none"


class AuthPlain(Auth):
    def __init__(self, plain):
        self.plain = plain

    def match(self, password: Optional[str]) -> bool:
        return self.plain == password

    @classmethod
    def algo_security(cls) -> int:
        return 10

    @classmethod
    def algo_name(cls) -> str:
        return "plain"


class AuthHash(Auth, ABC):
    SEP = "$"
    FMT = "{}" + SEP + "{}" + SEP + "{}"

    @classmethod
    @abstractmethod
    def algorithm_id(cls) -> str:
        pass

    @classmethod
    def algo_name(cls) -> str:
        return "hash"

    def __init__(self, algo_id: str, salt: b64, hash: b64):
        self.algo_id = algo_id
        self.salt = salt
        self.hash = hash

    def __str__(self):
        return AuthHash.FMT.format(
            self.algo_id,
            self.salt,
            self.hash
        )

    def __eq__(self, other: 'AuthHash'):
        return self.algo_id == other.algo_id and \
            self.salt == other.salt and \
            self.hash == other.hash


class AuthScrypt(AuthHash):

    ALGORITHM_ID = "1"

    @classmethod
    def algorithm_id(cls) -> str:
        return AuthScrypt.ALGORITHM_ID

    @staticmethod
    def new(plain: str):
        salt_b, hash_b = scrypt_new(plain, salt_length=16)
        salt_s, hash_s = bytes_to_b64(salt_b), bytes_to_b64(hash_b)
        return AuthScrypt(AuthScrypt.ALGORITHM_ID, salt_s, hash_s)

    def match(self, password: Optional[str]) -> bool:
        hash_b = scrypt(password, self.salt)
        hash_s = bytes_to_b64(hash_b)
        return self == AuthScrypt(AuthScrypt.ALGORITHM_ID, self.salt, hash_s)

    def algo_security(self) -> int:
        return 100


class AuthFactory:

    @staticmethod
    def parse(cipher: str) -> Optional[Auth]:
        if not cipher:
            # No authentication
            return AuthNone()

        # Parse 'smart': figure out if we are treating an hash or plain password
        # This introduce a limit: a plain password can't have the form
        # of an hash (<algoid>$<salt>$<hash>) and be treated as a plain password

        parts = cipher.split(AuthHash.SEP)

        if len(parts) == 3:
            try:
                algo_id = parts[0]
                if algo_id == AuthScrypt.algorithm_id():
                    return AuthScrypt(algo_id, parts[1], parts[2])

            except ValueError:
                pass

        # The 'cipher' doesn't have an hash form: treat it as plaintext
        return AuthPlain(cipher)


if __name__ == "__main__":
    plaintext = "hello"

    # Plain auth check
    assert AuthFactory.parse(plaintext).match(plaintext)

    # --

    auth_enc1 = AuthScrypt.new(plaintext)
    auth_enc2 = AuthScrypt.new(plaintext)

    # Two consecutive creations should be different
    assert str(auth_enc1) != str(auth_enc2)

    # --

    auth_str = str(auth_enc1)
    auth_dec = AuthFactory.parse(auth_str)

    # Are we parsing correctly?
    assert str(auth_dec) == auth_str

    # --

    # Match against plaintext
    assert auth_dec.match(plaintext)
