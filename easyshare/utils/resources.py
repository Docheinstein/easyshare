import pkgutil

from easyshare.logging import get_logger
from easyshare.utils.types import btos

log = get_logger(__name__)


def read_resource_string(pkg: str, res: str) -> str:
    """ Reads the content of the file 'res' from the resources of the package """
    b = pkgutil.get_data(pkg, res)
    if not b:
        log.w(f"Failed to load resource '{res}'")
        return ""
    return btos(b)
