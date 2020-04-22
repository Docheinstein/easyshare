from enum import Enum
from typing import Tuple, Optional

AUTH_SEP = "$"
AUTH_FMT = "{}" + AUTH_SEP + "{}" + AUTH_SEP + "{}"


class AuthType(Enum):
    SCRYPT = "1"

    @staticmethod
    def from_auth_string(s: str) -> Optional['AuthType']:
        if s.startswith(AuthType.SCRYPT.value):
            return AuthType.SCRYPT
        return None


def create_auth_string(auth_type: AuthType, salt: str, hashed: str) -> str:
    return "{}{}{}{}{}".format(
        auth_type.value,
        AUTH_SEP,
        salt,
        AUTH_SEP,
        hashed
    )


def parse_auth_string(auth_string: str) -> Optional[Tuple[AuthType, str, str]]:
    parts = auth_string.split(AUTH_SEP)
    if len(parts) != 3:
        return None

    return AuthType(parts[0]), parts[1], parts[2]
