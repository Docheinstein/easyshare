from abc import ABC, abstractmethod
from typing import Optional

from easyshare.utils.crypt import scrypt_new, bytes_to_b64, scrypt, b64



class Auth(ABC):
    """
    Base class of an authentication mechanism which is able to say
    whether, given a password, it matches or not the expected value.
    """
    @abstractmethod
    def authenticate(self, password: Optional[str]) -> bool:
        """ Returns true if the authentication succeed """
        pass

    @classmethod
    @abstractmethod
    def algo_security(cls) -> int:
        """
        Returns an integer that is greater the more great
        is the security of the authentication algorithm
        """
        pass

    @classmethod
    @abstractmethod
    def algo_type(cls) -> str:
        """
        Returns the name of the authentication algorithm
        """
        pass


class AuthNone(Auth):
    """ No authentication """
    def authenticate(self, password: Optional[str]) -> bool:
        # Always authenticated
        return True

    @classmethod
    def algo_security(cls) -> int:
        return 0

    @classmethod
    def algo_type(cls) -> str:
        return "none"

    def __str__(self):
        return ""


class AuthPlain(Auth):
    """ Authentication with a plain password """

    def __init__(self, plain):
        self.plain = plain

    def authenticate(self, password: Optional[str]) -> bool:
        # Authenticate if the string matches
        return self.plain == password

    @classmethod
    def algo_security(cls) -> int:
        return 10

    @classmethod
    def algo_type(cls) -> str:
        return "plain"

    def __str__(self):
        return self.plain


class AuthHash(Auth, ABC):
    """ Authentication through the comparison of two hashes """

    SEP = "$"
    FMT = "{}" + SEP + "{}" + SEP + "{}"

    @classmethod
    @abstractmethod
    def hashalgo_id(cls) -> str:
        """
        Returns the identifier of the hash algorithm, which will
        be inserted in the final hash for identify the used algo
        """
        pass

    @classmethod
    def algo_type(cls) -> str:
        return "secure hash"

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
    """ Concrete implementation of 'AuthHash' that use scrypt as hash algo """

    SCRYPT_ID = "1"

    @classmethod
    def hashalgo_id(cls) -> str:
        return AuthScrypt.SCRYPT_ID

    @staticmethod
    def new(plain: str):
        salt_b, hash_b = scrypt_new(plain, salt_length=16)
        salt_s, hash_s = bytes_to_b64(salt_b), bytes_to_b64(hash_b)
        return AuthScrypt(AuthScrypt.SCRYPT_ID, salt_s, hash_s)

    def authenticate(self, password: Optional[str]) -> bool:
        hash_b = scrypt(password, self.salt)
        hash_s = bytes_to_b64(hash_b)
        return self == AuthScrypt(AuthScrypt.SCRYPT_ID, self.salt, hash_s)

    def algo_security(self) -> int:
        return 100


class AuthFactory:

    @staticmethod
    def parse(cipher: str) -> Optional[Auth]:
        """
        Returns the appropriate authenticator for the given ciphertext.
        The logic is that if the ciphertext has the form ..$...$.. then it is
        an hash algorithm whose id is the first field.
        Otherwise it is considered a plain auth (unless cipher is invalid)
        """
        if not cipher:
            # No authentication
            return AuthNone()

        # Parse 'smart': figure out if we are treating an hash or plain password
        # This introduce a limit: a plain password can't have the form
        # of an hash (<hashalgo_id>$<salt>$<hash>) and be treated as a plain password

        parts = cipher.split(AuthHash.SEP)

        if len(parts) == 3:
            try:
                algo_id = parts[0]
                if algo_id == AuthScrypt.hashalgo_id():
                    return AuthScrypt(algo_id, parts[1], parts[2])

            except ValueError:
                pass

        # The 'cipher' doesn't have an hash form: treat it as plaintext
        return AuthPlain(cipher)