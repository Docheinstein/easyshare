def decorator(func):
    def wrapper(*args, **kwargs):
        print("<before>")
        func(*args, **kwargs)
        print("<after>")
    return wrapper


@decorator
def foo(x):
    print("Your string: " + x)


def classmethod_decorator(func):
    def wrapper(self, *args, **kwargs):
        print("<before>")
        func(self, *args, **kwargs)
        print("<after>")
        print("a: " + str(self.a))
    return wrapper


class AnyClass:
    def __init__(self):
        self.a = 4

    @classmethod_decorator
    def fool(self, x):
        print("You class string: " + x)


def classdec(arg1):

    print("classdec", arg1)

    return arg1


@classdec("ls")
class Command:
    pass


if __name__ == "__main__":
    # foo("ciao")
    # Command().name
    Command()