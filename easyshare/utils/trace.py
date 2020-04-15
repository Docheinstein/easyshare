from typing import Dict, List, Any, Tuple, Union

from easyshare.utils.str import strstr


def args_to_str(vargs: Union[List[Any], Tuple[Any, ...]] = None, kwargs: Dict[str, Any] = None):
    vargs_strs = [strstr(x) for x in list(vargs)] if vargs else []
    kwargs_strs = [str(k) + "=" + strstr(v) for k, v in kwargs.items()] if kwargs else []
    return ", ".join(vargs_strs + kwargs_strs)
