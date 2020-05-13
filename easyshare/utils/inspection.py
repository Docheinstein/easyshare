import traceback
from typing import Union, List, Tuple, Any, Dict

from easyshare.consts import ansi
from easyshare.utils.str import strstr


def func_args_to_str(vargs: Union[List[Any], Tuple[Any, ...]] = None,
                      kwargs: Dict[str, Any] = None):
    vargs_strs = [strstr(x) for x in list(vargs)] if vargs else []
    kwargs_strs = [str(k) + "=" + strstr(v) for k, v in kwargs.items()] if kwargs else []
    return ", ".join(vargs_strs + kwargs_strs)

def print_stack(color: ansi.ansi_fg = ansi.FG_CYAN):
    if color:
        print(color)
    traceback.print_stack()
    if color:
        print(ansi.RESET)