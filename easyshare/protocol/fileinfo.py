from typing import Dict, Union

from easyshare.protocol.filetype import FileType

# It would be wonderful to use TypedDict type as of PEP 526
# https://www.python.org/dev/peps/pep-0526/
# But it is supported only from python 3.8

FileInfo = Dict[str, Union[str, FileType, int]]
#   name: str
#   ftype: FileType
#   size: int
