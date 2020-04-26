from easyshare.utils.colors import magenta, cyan


_tracing = False


def enable_tracing(enabled: bool = True):
    global _tracing
    tracing = enabled


def is_tracing_enabled() -> bool:
    return _tracing


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
    if _tracing:
        print(msg, *args, **kwargs)

