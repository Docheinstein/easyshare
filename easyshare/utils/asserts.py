def assert_true(cond, msg: str = None):
    if cond is not True:
        raise AssertionError(msg)

def assert_false(cond, msg: str = None):
    if cond is not False:
        raise AssertionError(msg)

def assert_null(cond, msg: str = None):
    if cond is not None:
        raise AssertionError(msg)

def assert_valid(cond, msg: str = None):
    if not cond:
        raise AssertionError(msg)