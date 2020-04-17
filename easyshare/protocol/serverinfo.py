from typing import List, Union, Dict

from easyshare.protocol.sharinginfo import SharingInfo

try:
    # From python 3.8
    from typing import TypedDict

    class ServerInfo(TypedDict):
        uri: str
        name: str
        ip: str
        port: int
        sharings: List[SharingInfo]
except:
    ServerInfo = Dict[str, Union[str, int, List[SharingInfo]]]
