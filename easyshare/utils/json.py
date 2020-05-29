import json
from json import JSONDecodeError
from typing import Union, Optional

from easyshare.utils.types import str_to_bytes


def json_to_str(d: Union[dict, list, tuple], pretty=False) -> Optional[str]:
    if pretty:
        return json.dumps(d, indent=3)
    return json.dumps(d, separators=(",", ":"))


def json_to_pretty_str(d: Union[dict, list, tuple]) -> str:
    return json_to_str(d, pretty=True)


def json_to_bytes(d: Union[dict, list, tuple]) -> Optional[bytes]:
    return str_to_bytes(json_to_str(d))


def str_to_json(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except JSONDecodeError:
        return None


def bytes_to_json(b: Union[bytearray, bytes]) -> Optional[dict]:
    try:
        return json.loads(b)
    except JSONDecodeError:
        return None

# shortcuts
j = json_to_pretty_str
jtos = json_to_str
jtob = json_to_bytes
stoj = str_to_json
btoj = bytes_to_json