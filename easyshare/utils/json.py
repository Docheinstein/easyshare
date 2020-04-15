import json

from easyshare.utils.types import str_to_bytes


def json_to_str(d: dict, pretty=False) -> str:
    if pretty:
        return json.dumps(d, indent=4)
    return json.dumps(d, separators=(",", ":"))


def json_to_pretty_str(d: dict, pretty=False) -> str:
    return json_to_str(d, pretty=True)


def json_to_bytes(d: dict) -> bytes:
    return str_to_bytes(json_to_str(d))


def str_to_json(s: str) -> dict:
    return json.loads(s)


def bytes_to_json(b: bytes) -> dict:
    return json.loads(b)

