from abc import ABC, abstractmethod
from typing import List, Any, Optional, Union, Tuple

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.str import unprefix
from easyshare.utils.types import to_int, list_wrap

log = get_logger(__name__, level=logging.LEVEL_INFO)


class ArgParamsParser(ABC):
    @abstractmethod
    def required_parameters_count(self) -> int:
        pass

    @abstractmethod
    def parse_parameters(self, params: Optional[List[str]]) -> Any:
        pass


class IntArgParamsParser(ArgParamsParser):
    def required_parameters_count(self) -> int:
        return 1

    def parse_parameters(self, params: Optional[str]) -> Any:
        return to_int(params[0], raise_exceptions=True)


class PresenceIntArgParamsParser(ArgParamsParser):
    def required_parameters_count(self) -> int:
        return 0

    def parse_parameters(self, _: Optional[List[str]]) -> Any:
        return True


class ArgSpec:
    def __init__(self,
                 aliases: Union[str, List[str]],
                 params_parser: ArgParamsParser):

        self.aliases: List[str] = list_wrap(aliases)
        self.params_parser: ArgParamsParser = params_parser


class Args:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def __str__(self):
        return json_to_pretty_str(self.cfg)

    def __contains__(self, item):
        return self.has_kwarg(item)

    # Positional arguments

    def has_vargs(self) -> bool:
        return True if self.get_vargs() is not None else False

    def get_vargs(self, default=None) -> List[Any]:
        return self.cfg.get(None, default)

    # Keyword arguments

    def has_kwarg(self, aliases: Union[str, List[str]]) -> bool:
        return True if self.get_kwarg_params(aliases) is not None else None

    def get_kwarg_param(self, aliases: Union[str, List[str]], default=None) -> List[Any]:
        params = self.get_kwarg_params(aliases)
        if params:
            return params[0]
        return default

    def get_kwarg_params(self, aliases: Union[str, List[str]], default=None) -> List[Any]:
        for alias in list_wrap(aliases):
            if alias in self.cfg:
                return self.cfg.get(alias)

        return default

    @staticmethod
    def parse(args: List[str], args_specs: List[ArgSpec]) -> Optional['Args']:
        cfg = {}

        def get_bucket(arg_name: str) -> Tuple[Optional[List], Optional[ArgSpec]]:
            nonlocal cfg

            log.d("get_bucket (%s)", arg_name)

            for arg_spec in args_specs:
                if arg_name in arg_spec.aliases:

                    # Found an alias that matches the argument name
                    log.i("%s", arg_name)

                    # Check whether this argument was already found,
                    # if not allocate a new list using this arg_name
                    # Check for every alias
                    bck = None
                    for a_arg_alias in arg_spec.aliases:
                        if a_arg_alias in cfg:
                            bck = cfg.get(a_arg_alias)
                            break

                    # If bucket is still None, then we have to allocate it
                    if not bck:
                        bck = []
                        cfg[arg_name] = bck

                    log.d("Returning bucket for %s", arg_name)

                    return bck, arg_spec

            return None, None

        log.i("Parsing arguments: %s", args)


        try:
            cfg = {}

            i = 0
            while i < len(args):
                arg = args[i]

                log.d("Inspecting argument %s", arg)

                if arg.startswith("--") and len(arg) > 2:
                    # Long format
                    arg_name = arg

                    # Check whether this is a known argument
                    bucket, argspec = get_bucket(arg_name)

                    if bucket is not None:
                        # Ensure that we have enough params to provide
                        # to the params parser of this argument
                        params_count = argspec.params_parser.required_parameters_count()

                        if i + params_count >= len(args):
                            log.e("Not enough parameters to feed argument '%s'", arg_name)
                            raise IndexError("not enough parameters to feed argument")

                        # Provide the params to the parser, and add
                        # the parsed value to the bucket
                        val = argspec.params_parser.parse_parameters(
                            args[(i + 1):(i + 1 + params_count)]
                        )

                        log.i("> %s", "{}".format(val))
                        bucket.append(val)

                        i += params_count
                    else:
                        log.w("Unknown argument: '%s'", arg_name)

                elif arg.startswith("-") and len(arg) > 1:
                    # Short format: allow concatenation of arguments (as letters)

                    args_chain = unprefix(arg, "-")
                    chain_idx = 0

                    while chain_idx < len(args_chain):
                        c_arg_name = "-" + args_chain[chain_idx]

                        # Check whether this is a known argument
                        bucket, argspec = get_bucket(c_arg_name)
                        if bucket is not None:
                            # We can feed the parser only if we are on the
                            # last param of the chain, otherwise params_count
                            # must be 0
                            params_count = argspec.params_parser.required_parameters_count()

                            if params_count > 0 and chain_idx < len(args_chain) - 1:
                                # Not on the last one, cannot provide params
                                log.e("Cannot feed parameter '%s' in the middle of an argument chain", c_arg_name)
                                raise Exception("cannot feed parameter in the middle of an argument chain")

                            if i + params_count >= len(args):
                                log.e("Not enough parameters to feed argument '%s'", c_arg_name)
                                raise Exception("not enough parameters to feed argument")

                            val = argspec.params_parser.parse_parameters(
                                args[(i + 1):(i + 1 + params_count)]
                            )

                            log.i("> %s", "{}".format(val))
                            bucket.append(val)

                            i += params_count
                        else:
                            log.w("Unknown argument in chain: '%s'", c_arg_name)

                        chain_idx += 1

                else:
                    log.d("Adding '%s' as positional parameter", arg)
                    bucket = cfg.setdefault(None, [])
                    bucket.append(arg)

                i += 1
        except Exception as ex:
            log.e("Exception occurred while parsing: %s", ex)
            return None

        return Args(cfg)


PARAM_INT = IntArgParamsParser()
PARAM_PRESENCE = PresenceIntArgParamsParser()


if __name__ == "__main__":
    def main():
        args = Args.parse(
            args=["-v", "5", "randomstring", "--trace", "-p", "6666"],
            args_specs=[
                ArgSpec(aliases=["-v", "--verbose"], params_parser=PARAM_INT),
                ArgSpec(aliases=["-t", "--trace"], params_parser=PARAM_PRESENCE),
                ArgSpec(aliases=["-r", "--reverse"], params_parser=PARAM_PRESENCE),
                ArgSpec(aliases=["-g", "--group"], params_parser=PARAM_PRESENCE),
                ArgSpec(aliases=["-l", "--long"], params_parser=PARAM_PRESENCE),
                ArgSpec(aliases=["-p", "--port"], params_parser=PARAM_INT)
            ]
        )

        if args:
            print(args)

            print(args.get_kwarg_param("-v"))
            print(args.get_kwarg_param(["-t", "--trace"]))
            print(args.has_vargs())
            print(args.get_vargs())

    main()