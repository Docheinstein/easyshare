from typing import List, TypedDict


class ServerInfo(TypedDict):
    uri: str
    name: str
    ip: str
    port: int
    sharings: List[str]
