import traceback
from typing import Union, List, Tuple, Any, Dict

from easyshare.consts import ansi
from easyshare.styling import fg
from easyshare.utils.types import is_str


def func_args_to_str(vargs: Union[List[Any], Tuple[Any, ...]] = None,
                      kwargs: Dict[str, Any] = None):
    """
    Returns the function args and kwargs as string.
    e.g. "param1", 5, port=12932, address="the-address"
    """

    def quote_string(s: str) -> str:
        return "\"" + s + "\"" if is_str(s) else str(s)

    vargs_strs = [quote_string(x) for x in list(vargs)] if vargs else []
    kwargs_strs = [str(k) + "=" + quote_string(v) for k, v in kwargs.items()] if kwargs else []
    return ", ".join(vargs_strs + kwargs_strs)

def stacktrace(color: str = None):
    return fg("\n".join(traceback.format_stack()), color)

if __name__ == "__main__":
    print(stacktrace())