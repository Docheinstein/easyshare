def assert_true(cond, msg: str = None):
    """ Raise an AssertionError if cond is not True """
    if cond is not True:
        raise AssertionError(msg)

def assert_false(cond, msg: str = None):
    """ Raise an AssertionError if cond is not False """
    if cond is not False:
        raise AssertionError(msg)

def assert_null(cond, msg: str = None):
    """ Raise an AssertionError if cond is not None """
    if cond is not None:
        raise AssertionError(msg)

def assert_valid(cond, msg: str = None):
    """ Raise an AssertionError if cond evaluates to False """
    if not cond:
        raise AssertionError(msg)