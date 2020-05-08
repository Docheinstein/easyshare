from typing import List, Union, Dict

from easyshare.protocol.sharinginfo import SharingInfo

try:
    # From python 3.8
    from typing import TypedDict

    class ServerInfo(TypedDict):
        # Don't expose IP and port

        name: str
        # ip: str
        # port: int
        # discoverable: bool
        # discover_port: int
        ssl: bool
        auth: bool
        sharings: List[SharingInfo]

    class ServerInfoFull(ServerInfo):
        ip: str
        port: int

        discoverable: bool
        discover_port: int
except:
    ServerInfo = Dict[str, Union[str, int, List[SharingInfo]]]
