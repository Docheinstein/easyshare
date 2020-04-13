tracing = False


def trace_out(ip, port, name, what, *args, **kwargs):
    _trace(">> {}:{} ({})\n>>   {}".format(
        ip, port, name, what
    ), *args, **kwargs)


def trace_in(msg, *args, **kwargs):
    _trace("<< " + msg, *args, **kwargs)


def _trace(msg, *args, **kwargs):
    if tracing:
        print(msg, *args, **kwargs)


def init_tracing(enabled: bool = True):
    global tracing
    tracing = enabled


def is_tracing_enabled() -> bool:
    global tracing
    return tracing
