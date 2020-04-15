from easyshare.utils.colors import magenta, cyan

tracing = False


def trace_out(message: str, ip: str, port: int, alias: str = None):
    _trace(
        magenta(
            ">> {}:{}{}\n>>   {}".format(
                ip,
                port,
                " (" + alias + ")" if alias else "",
                message
            ),
        )
    )


def trace_in(message: str, ip: str, port: int, alias: str = None):
    _trace(
        cyan(
            "<< {}:{}{}\n<<   {}".format(
                ip,
                port,
                " (" + alias + ")" if alias else "",
                message
            ),
        )
    )


def _trace(msg, *args, **kwargs):
    if tracing:
        print(msg, *args, **kwargs)


def init_tracing(enabled: bool = True):
    global tracing
    tracing = enabled


def is_tracing_enabled() -> bool:
    return tracing
