from typing import Union

from easyshare.common import TransferDirection, TransferProtocol
from easyshare.consts import ansi
from easyshare.endpoint import Endpoint
from easyshare.styling import fg
from easyshare.utils.mathematics import rangify

TRACING_NONE = 0
TRACING_TEXT = 1
TRACING_BIN_PAYLOADS = 2
TRACING_BIN_ALL = 3

TRACING_MIN = 0
TRACING_MAX = TRACING_BIN_ALL

_tracing = TRACING_NONE

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


""" e.g. TRACING_BIN_PAYLOAD/TRACING_BIN_ALL
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


def get_tracing_level() -> int:
    return _tracing


def set_tracing_level(level: int):
    global _tracing
    _tracing = rangify(level, TRACING_MIN, TRACING_MAX)



def trace_text(what: str, sender: Endpoint, receiver: Endpoint,
               direction: TransferDirection, protocol: TransferProtocol):
    if _tracing < TRACING_TEXT:
        return

    _trace(what, sender, receiver, direction, protocol)


def trace_bin_payload(what: Union[bytes, bytearray], sender: Endpoint, receiver: Endpoint,
                      direction: TransferDirection, protocol: TransferProtocol):
    if _tracing < TRACING_BIN_PAYLOADS:
        return

    _trace(_hexdump(what), sender, receiver, direction, protocol)


def trace_bin_all(what: Union[bytes, bytearray], sender: Endpoint, receiver: Endpoint,
                  direction: TransferDirection, protocol: TransferProtocol):
    if _tracing < TRACING_BIN_ALL:
        return

    _trace(_hexdump(what), sender, receiver, direction, protocol)

def _trace(what: str, sender: Endpoint, receiver: Endpoint,
               direction: TransferDirection, protocol: TransferProtocol):

    if direction == TransferDirection.OUT:
        _1 = ">>"
        _2 = ""
        color = ansi.FG_MAGENTA
    else:
        _1 = "<<"
        _2 = "="
        color = ansi.FG_CYAN
    try:
        print(fg(f"""\
{_1} ============================== {direction.value} ==============================={_2}
{_1} From:      {sender[0]}:{sender[1]}
{_1} To:        {receiver[0]}:{receiver[1]}
{_1} Protocol:  {protocol.value}
{_1} ------------------------------------------------------------------
{what}""", color=color))
    except OSError:
        # EWOULDBLOCK may arise for large messages (subprocess.Popen with streams)
        # In the worst case the tracing will fail, but do not arise
        # an exception for this reason
        pass

def _hexdump(what: Union[bytes, bytearray]):
    # c6 f2 31 44 5d ca 5d 1d  f0 75 97 f5 85 77 69 3d  |..1D].]..u...wi=|

    dump = ""

    in_line_idx = 0
    hexs = [""] * 16
    asciis = [""] * 16

    bi = 0

    what_hex = what.hex()
    what_len = len(what)

    if len(what_hex) != what_len * 2:
        # WTF
        return repr(what)

    def dump_line(count: int = 16):
        nonlocal dump

        if dump:
            dump += "\n"

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
        in_line_idx = (in_line_idx + 1) % 16

        if in_line_idx == 0:
            dump_line()

    if in_line_idx > 0:
        dump_line(in_line_idx - 1)

    return dump
