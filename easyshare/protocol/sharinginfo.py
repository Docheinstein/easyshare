from typing import Dict, Union

from easyshare.protocol.filetype import FileType

try:
    # From python 3.8
    from typing import TypedDict

    class SharingInfo(TypedDict):
        name: str
        ftype: FileType
        read_only: bool
        authentication: bool
except:
    SharingInfo = Dict[str, Union[str, FileType, bool]]
