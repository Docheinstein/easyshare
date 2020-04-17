from typing import Dict, Union

from easyshare.protocol.filetype import FileType

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict):
        name: str
        ftype: FileType
        size: int
except:
    FileInfo = Dict[str, Union[str, FileType, int]]
