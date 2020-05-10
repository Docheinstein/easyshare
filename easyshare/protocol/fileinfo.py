from typing import Dict, Union, List

from easyshare.protocol.filetype import FileType
from easyshare.utils.tree import TreeNodeDict

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict, total=False):
        name: str
        ftype: FileType
        size: int
        mtime: int

    class FileInfoTreeNode(FileInfo, TreeNodeDict, total=False):
        pass

except:
    FileInfo = Dict[str, Union[str, FileType, int]]
    FileInfoNode = Dict[str, Union[str, FileType, int, List['FileInfoNode']]]
