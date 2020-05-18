import inspect


def decorator_outer(fun):
    print("BEGIN DEF decorator_outer")
    def wrapper_outer():
        print("BEGIN CALL wrapper_outer __name__, ", fun.__name__)
        # print("BEGIN CALL wrapper_outer __trace_name, ", fun.__trace_name)
        fun()
        print("END CALL wrapper_outer")
    print("END DEF decorator_outer")
    return wrapper_outer

def decorator_inner(fun):
    print("BEGIN DEF decorator_inner")
    def wrapper_inner():
        print("BEGIN CALL wrapper_inner __name__, ", fun.__name__)
        fun()
        print("END CALL wrapper_inner")
    print("END DEF decorator_inner")

    # wrapper_inner.__name__ = fun.__name__

    return wrapper_inner

# def decoratore_traceable(fun):
#     print("BEGIN DEF decoratore_traceable")
#     def wrapper_traceable():
#         print("BEGIN CALL wrapper_traceable __name__, ", fun.__name__)
#         fun()
#         print("END CALL wrapper_traceable")
#     print("END DEF decoratore_traceable")


@decorator_outer
@decorator_inner
def api():
    print("API")


if __name__ == "__main__":
    api()