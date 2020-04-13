from typing import List, Union, Dict

from easyshare.protocol.sharinginfo import SharingInfo

ServerInfo = Dict[str, Union[str, int, List[SharingInfo]]]
#   uri: str
#   name: str
#   ip: str
#   port: int
#   sharings: List[SharingInfo]
