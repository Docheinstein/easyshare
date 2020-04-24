import inspect


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


def outer(api):
    def wrapper_outer():
        print("outer (given api: '{}\n{}')".format(api.__name__, dir(api)))
        print("getfullargspec: ", inspect.getfullargspec(api))
        api()
    return wrapper_outer


def middle(api):
    def wrapper_middle():
        print("middle (given api: '{}\n{}')".format(api.__name__, dir(api)))
        print("__code__: ", api.__code__)
        print("__closure__: ", api.__closure__)
        print("__qualname__: ", api.__qualname__)
        print("__annotations__: ", api.__annotations__)
        api()
    return wrapper_middle


def inner(api):
    def wrapper_inner():
        print("inner (given api: '{}')".format(api.__name__))
        print("__code__: ", api.__code__)
        print("__closure__: ", api.__closure__)
        print("__qualname__: ", api.__qualname__)
        print("__annotations__: ", api.__annotations__)
        api()
    return wrapper_inner


@outer
@middle
@inner
def my_api():
    print("THIS IS THE API",)


if __name__ == "__main__":
    # foo("ciao")
    # Command().name
    # Command()
    my_api()
