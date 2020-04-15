import inspect


def do_sum(*args):
    print("do_sum current frame", inspect.currentframe().f_locals)
    outer_frames = inspect.getouterframes(inspect.currentframe())

    for f in outer_frames:
        print("do_sum current outer frame", f.frame.f_locals)

    stack = inspect.stack()
    for f in stack:
        print("do_sum current stack frame", f.frame.f_locals)

    return sum([int(x) for x in args])


def sum2(a: int, b: int):
    print("sum2 current frame", inspect.currentframe().f_locals)
    do_sum(a, b)


def trace_request():
    caller_frame = inspect.stack()[1].frame
    arg_names, vargs_names, kwargs_names, vals = inspect.getargvalues(caller_frame)

    print("caller_frame: ", caller_frame.f_code.co_name)


def foo(a, b, flags=None):
    trace_request()


if __name__ == "__main__":
    # sum2(5, 8)
    foo(5, "ciao")