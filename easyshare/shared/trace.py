from easyshare.utils.colors import magenta, cyan

tracing = False


def trace_out(ip: str, port: int, name: str, message: str):
    _trace(
        magenta(">> {}:{} ({})\n>>   {}".format(
            ip, port, name, message))
    )


def trace_in(ip: str, port: int, name: str, message: str):
    _trace(
        cyan("<< {}:{} ({})\n<<   {}".format(
            ip, port, name, message))
    )


def _trace(msg, *args, **kwargs):
    if tracing:
        print(msg, *args, **kwargs)


def init_tracing(enabled: bool = True):
    global tracing
    tracing = enabled


def is_tracing_enabled() -> bool:
    return tracing
