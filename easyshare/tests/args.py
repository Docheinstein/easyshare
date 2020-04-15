
def foo(a, *args, **kwargs):
    print(list(args))
    print(kwargs)


if __name__ == "__main__":
    foo("ciao", "bella", pippo="pippo", pluto="pluto")