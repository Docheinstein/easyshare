from enum import Enum
from typing import Tuple, Optional

AUTH_SEP = "$"
AUTH_FMT = "{}" + AUTH_SEP + "{}" + AUTH_SEP + "{}"


class AuthType(Enum):
    SCRYPT = "1"


def create_auth_string(auth_type: AuthType, salt: str, hashed: str) -> str:
    return "{}${}${}".format(
        auth_type.value,
        salt,
        hashed
    )


def parse_auth_string(auth_string: str) -> Optional[Tuple[AuthType, str, str]]:
    parts = auth_string.split(AUTH_SEP)
    if len(parts) != 3:
        return None

    return AuthType(parts[0]), parts[1], parts[2]
