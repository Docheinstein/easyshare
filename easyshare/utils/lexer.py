import re
import shlex
from typing import List


def split(string: str) -> List[str]:
    return shlex.split(string)


# Taken from shlex, but allowing quote_char overriding

# _find_unsafe = re.compile(r'[^\w@%+=:,./-]', re.ASCII).search
_find_unsafe = re.compile(r'[^\w\'"]', re.ASCII).search

def join(parts: List[str], quote_char="'") -> str:
    def shlex_join(split_command, quote_func=lambda p: p):
        """Return a shell-escaped string from *split_command*."""
        return ' '.join(quote_func(arg) for arg in split_command)

    if not quote_char:
        return shlex_join(parts)

    if quote_char not in ["'", "\""]:
        raise ValueError(f"Invalid quote character {quote_char}")

    q = quote_char
    nq = "'" if q == "\"" else "\""

    def shlex_quote(s):
        """Return a shell-escaped version of the string *s*."""
        if not s:
            return q * 2

        if _find_unsafe(s) is None:
            return s

        # use single quotes, and put single quotes into double quotes
        # the string $'b is then quoted as '$'"'"'b'

        return q + s.replace(q, q + nq + q + nq + q) + q

    return shlex_join(parts, quote_func = shlex_quote)