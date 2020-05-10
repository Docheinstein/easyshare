def items(obj: object) -> dict:
    return {k: v for k, v in obj.__dict__.items() if "__" not in k}


def keys(obj: object) -> list:
    return [k for k, v in obj.__dict__.items() if "__" not in k]


def values(obj: object) -> list:
    return [v for k, v in obj.__dict__.items() if "__" not in k]