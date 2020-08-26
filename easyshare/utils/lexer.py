import re
import shlex
from typing import List

from easyshare.logging import get_logger

log = get_logger(__name__)

def split(string: str, keepquotes=False) -> List[str]:
    """
    Parsing Rules

    When operating in non-POSIX mode, shlex will try to obey to the following rules.
        Quote characters are not recognized within words (Do"Not"Separate is parsed as the single word Do"Not"Separate);
        Escape characters are not recognized;
        Enclosing characters in quotes preserve the literal value of all characters within the quotes;
        Closing quotes separate words ("Do"Separate is parsed as "Do" and Separate);
        If whitespace_split is False, any character not declared to be a word character, whitespace, or a quote will be returned as a single-character token. If it is True, shlex will only split words in whitespaces;
        EOF is signaled with an empty string ('');
        It’s not possible to parse empty strings, even if quoted.

    When operating in POSIX mode, shlex will try to obey to the following parsing rules.
        Quotes are stripped out, and do not separate words ("Do"Not"Separate" is parsed as the single word DoNotSeparate);
        Non-quoted escape characters (e.g. '\') preserve the literal value of the next character that follows;
        Enclosing characters in quotes which are not part of escapedquotes (e.g. "'") preserve the literal value of all characters within the quotes;
        Enclosing characters in quotes which are part of escapedquotes (e.g. '"') preserves the literal value of all characters within the quotes, with the exception of the characters mentioned in escape. The escape characters retain its special meaning only when followed by the quote in use, or the escape character itself. Otherwise the escape character will be considered a normal character.
        EOF is signaled with a None value;
        Quoted empty strings ('') are allowed.

    """
    log.d(f"lexer.split({string}, keepquotes={keepquotes})")

    if keepquotes:
        return shlex.split(string, posix=False)

    return shlex.split(string, posix=True)



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