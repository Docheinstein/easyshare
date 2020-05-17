import pkgutil

from easyshare.logging import get_logger
from easyshare.utils.types import bytes_to_str

log = get_logger(__name__)


def read_resource_string(pkg: str, res: str) -> str:
    """ Reads the content of the file 'res' from the resources of the package """
    b = pkgutil.get_data(pkg, res)
    if not b:
        log.w("Failed to load resource '%s'", res)
        return ""
    return bytes_to_str(b)
