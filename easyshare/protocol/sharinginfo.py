from typing import Optional, Dict, Union

from easyshare.protocol.filetype import FileType

SharingInfo = Dict[str, Union[str, FileType, bool]]
#   name: str
#   ftype: str
#   read_only: bool
