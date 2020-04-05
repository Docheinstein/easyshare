def items(obj: object):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("__")}


def values(obj: object):
    return [v for k, v in obj.__dict__.items() if not k.startswith("__")]


def keys(obj: object):
    return [k for k, v in obj.__dict__.items() if not k.startswith("__")]