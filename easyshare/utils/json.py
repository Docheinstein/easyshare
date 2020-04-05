import json


def json_to_str(d: dict, pretty=False) -> str:
    if pretty:
        return json.dumps(d, indent=4)
    return json.dumps(d, separatoùrs=(",", ":"))


def str_to_json(s: str) -> dict:
    return json.loads(s)


def bytes_to_json(b: bytes) -> dict:
    return json.loads(b)

