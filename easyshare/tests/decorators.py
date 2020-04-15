def decorator(func):
    def wrapper(*args, **kwargs):
        print("<before>")
        func(*args, **kwargs)
        print("<after>")
    return wrapper


@decorator
def foo(x):
    print("Your string: " + x)


def class_decorator(func):
    def wrapper(self, *args, **kwargs):
        print("<before>")
        func(self, *args, **kwargs)
        print("<after>")
        print("a: " + str(self.a))
    return wrapper


class AnyClass:
    def __init__(self):
        self.a = 4

    @class_decorator
    def fool(self, x):
        print("You class string: " + x)


if __name__ == "__main__":
    # foo("ciao")
    AnyClass().fool("hello")
