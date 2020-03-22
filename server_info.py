from typing import TypedDict, List


class EasyshareServerInfo(TypedDict):
    uri: str
    name: str
    address: str
    port: int
    sharings: List[str]
