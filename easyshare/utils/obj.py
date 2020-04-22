def items(obj: object) -> dict:
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("__")}


def values(obj: object) -> list:
    return [v for k, v in obj.__dict__.items() if not k.startswith("__")]


def keys(obj: object) -> list:
    return [k for k, v in obj.__dict__.items() if not k.startswith("__")]


if __name__ == "__main__":
    class CC:
        SORT = "ciao"

        def amethod(self):
            pass

    print(items(CC))