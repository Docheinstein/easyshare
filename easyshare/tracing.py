import time
from datetime import datetime
from typing import Union

from easyshare.common import TransferDirection, TransferProtocol, TRACING_TEXT, TRACING_BIN
from easyshare.consts import ansi
from easyshare.endpoint import Endpoint
from easyshare.settings import Settings, get_setting
from easyshare.styling import fg
from easyshare.utils import eprint
from easyshare.utils.json import j

""" e.g. TRACING_JSON
>> ========== OUT ============
>> From:     192.168.1.106:10243
>> To:       192.168.1.106:10243
>> Protocol: TCP
>> ---------------------------
{
    "success": True, 
    ....
}
>> ===========================
"""


""" e.g. TRACING_BIN
<< ========== IN =============
<< From:     192.168.1.106:10243
<< To:       192.168.1.106:10243
<< Protocol: TCP
<< ---------------------------
c6 f2 31 44 5d ca 5d 1d  f0 75 97 f5 85 77 69 3d  |..1D].]..u...wi=|
cc ed 9c 48 b3 1d d6 27  0d ae 77 b4 fe 46 e3 aa  |...H...'..w..F..|
...
<< ===========================
"""


def trace_json(what: Union[dict, list, tuple], sender: Endpoint, receiver: Endpoint,
               direction: TransferDirection, protocol: TransferProtocol,
               trace_type: str = "JSON") -> bool:
    if get_setting(Settings.TRACING) < TRACING_TEXT:
        return False

    _trace(j(what), sender, receiver, direction, protocol, trace_type=trace_type)
    return True


def trace_text(what: str, sender: Endpoint, receiver: Endpoint,
               direction: TransferDirection, protocol: TransferProtocol,
               trace_type: str = "Text") -> bool:
    if get_setting(Settings.TRACING) < TRACING_TEXT:
        return False

    _trace(what, sender, receiver, direction, protocol, trace_type=trace_type)
    return True


def trace_bin(what: Union[bytes, bytearray], sender: Endpoint, receiver: Endpoint,
              direction: TransferDirection, protocol: TransferProtocol,
              trace_type: str = "Binary") -> bool:
    if get_setting(Settings.TRACING) < TRACING_BIN:
        return False

    _trace(_hexdump(what), sender, receiver, direction,
           protocol, trace_type=trace_type, size=len(what))
    return True

def _trace(what: str,
           sender: Endpoint, receiver: Endpoint,
           direction: TransferDirection, protocol: TransferProtocol,
           trace_type: str = "Unknown", size: int = -1):

    if direction == TransferDirection.OUT:
        _1 = ">>"
        _2 = ""
        color = ansi.FG_MAGENTA
    else:
        _1 = "<<"
        _2 = "="
        color = ansi.FG_CYAN

    s = f"""\
{_1} ============================== {direction.value} ==============================={_2}
{_1} From:      {f'{sender[0]}:{sender[1]}' if sender else "-----------------"}
{_1} To:        {f'{receiver[0]}:{receiver[1]}' if receiver else "-----------------"}
{_1} Protocol:  {protocol.value}
{_1} Timestamp: {int(time.time_ns() * 1e-6)} ({datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")})"""

    if size >= 0:
        s += f"""
{_1} Size:      {size}"""

    if trace_type:
        s += f"""
{_1} Type:      {trace_type}"""

    s += f"""
{_1} ------------------------------------------------------------------
{what}"""

    try:
        eprint(fg(s, color=color))
    except OSError:
        # EWOULDBLOCK may arise for large messages (subprocess.Popen with streams)
        # In the worst case the tracing will fail, but do not arise
        # an exception for this reason
        pass

def _hexdump(what: Union[bytes, bytearray], show_position: bool = True):
    # c6 f2 31 44 5d ca 5d 1d  f0 75 97 f5 85 77 69 3d  |..1D].]..u...wi=|
    BYTES_PER_LINE = 16

    dump = ""

    in_line_idx = 0
    hexs = [""] * BYTES_PER_LINE
    asciis = [""] * BYTES_PER_LINE
    line_pos = 0

    bi = 0

    what_hex = what.hex()
    what_len = len(what)

    if len(what_hex) != what_len * 2:
        # WTF
        return repr(what)

    def dump_line(count: int = BYTES_PER_LINE):
        nonlocal dump

        if dump:
            dump += "\n"

        if show_position:
            dump += f"0x{line_pos:0{8}x}  |  "

        for i in range(8):
            hexstr = hexs[i] if i <= count else "  "
            dump += hexstr + " "

        dump += "  "

        for i in range(8, 16):
            hexstr = hexs[i] if i <= count else "  "
            dump += hexstr + " "

        dump += " |"

        for i in range(16):
            asciistr = asciis[i] if i <= count else " "
            if len(asciistr) != 1:
                asciistr = "."
            dump += asciistr

        dump += "|"


    while bi < what_len:
        hi = bi << 1
        byte = what[bi:bi+1]         # e.g. \x63

        hexs[in_line_idx] = what_hex[hi:hi+2] # e.g. "63"
        asciis[in_line_idx] = chr(byte[0]) if (32 <= byte[0] <= 126) else "." # eg "c"

        bi += 1
        in_line_idx = (in_line_idx + 1) % BYTES_PER_LINE

        if in_line_idx == 0:
            dump_line()
            line_pos += BYTES_PER_LINE

    if in_line_idx > 0:
        dump_line(in_line_idx - 1)

    return dump


if __name__ == "__main__":
    import easyshare.logging
    easyshare.logging.init_logging()
    print(_hexdump(open("/etc/passwd", "rb").read()))
