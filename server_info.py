from typing import TypedDict, List


class ServerInfo(TypedDict):
    uri: str
    name: str
    address: str
    port: int
    sharings: List[str]
