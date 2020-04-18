from typing import Dict, Union, List, Optional

from easyshare.protocol.filetype import FileType
from easyshare.tree.tree import TreeNodeDict

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict):
        name: str
        ftype: FileType
        size: int

    class FileInfoTreeNode(TypedDict, TreeNodeDict, total=False):
        pass

except:
    FileInfo = Dict[str, Union[str, FileType, int]]
    FileInfoNode = Dict[str, Union[str, FileType, int, List['FileInfoNode']]]
