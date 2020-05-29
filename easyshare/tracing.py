from easyshare.styling import magenta, cyan


_tracing = False


def enable_tracing(enabled: bool = True):
    """ Enables/disables the dump of packets """
    global _tracing
    _tracing = enabled


def is_tracing_enabled() -> bool:
    """ Returns whether the dump of packets is enabled """
    return _tracing


def trace_out(message: str, ip: str, port: int, alias: str = None):
    """ Dump an outgoing message, if tracing is enabled """
    _trace(magenta(f"""\
>> {ip}:{port}{' (' + alias + ')' if alias else ''}
>> {message}"""
))


def trace_in(message: str, ip: str, port: int, alias: str = None):
    """ Dump an ingoing message, if tracing is enabled """
    _trace(cyan(f"""\
<< {ip}:{port}{' (' + alias + ')' if alias else ''}
<< {message}"""
))


def _trace(msg, *args, **kwargs):
    if _tracing:
        try:
            print(msg, *args, **kwargs)
        except OSError:
            # EWOULDBLOCK may arise for large messages (subprocess.Popen with streams)
            # In the worst case the tracing will fail, but do not arise
            # an exception for this reason
            pass

