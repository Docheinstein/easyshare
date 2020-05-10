import json
from typing import Union

from easyshare.utils.types import str_to_bytes


def json_to_str(d: Union[dict, list, tuple], pretty=False) -> str:
    if pretty:
        return json.dumps(d, indent=4)
    return json.dumps(d, separators=(",", ":"))


def json_to_pretty_str(d: Union[dict, list, tuple]) -> str:
    return json_to_str(d, pretty=True)

j = json_to_pretty_str # shortcut alias


def json_to_bytes(d: Union[dict, list, tuple]) -> bytes:
    return str_to_bytes(json_to_str(d))


def str_to_json(s: str) -> dict:
    return json.loads(s)


def bytes_to_json(b: bytes) -> dict:
    return json.loads(b)

