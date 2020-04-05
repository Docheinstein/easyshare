
def items(obj):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("__")}


def values(obj):
    return [v for k, v in obj.__dict__.items() if not k.startswith("__")]


def keys(obj):
    return [k for k, v in obj.__dict__.items() if not k.startswith("__")]