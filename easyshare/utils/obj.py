def items(obj: object) -> dict:
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("__")}


def values(obj: object) -> list:
    return [v for k, v in obj.__dict__.items() if not k.startswith("__")]


def keys(obj: object) -> list:
    return [k for k, v in obj.__dict__.items() if not k.startswith("__")]
