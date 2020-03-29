from typing import TypedDict, List


class ServerInfo(TypedDict):
    uri: str
    name: str
    ip: str
    port: int
    sharings: List[str]
