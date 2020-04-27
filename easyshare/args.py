from abc import ABC, abstractmethod
from typing import List, Any, Optional, Union, Tuple, Callable, Dict

from easyshare.logging import get_logger
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.str import unprefix
from easyshare.utils.types import to_int, list_wrap

log = get_logger(__name__)


class ArgParamsParser(ABC):
    VARIADIC_PARAMETERS_COUNT = -1

    @abstractmethod
    def required_parameters_count(self) -> int:
        pass

    @abstractmethod
    def parse_parameters(self, params: Optional[List[str]]) -> Any:
        pass


class CustomArgParamsParser(ArgParamsParser):
    def __init__(self, params_count: int, params_parser: Callable[[Optional[List]], Any]):
        self._params_count = params_count
        self._params_parser = params_parser

    def required_parameters_count(self) -> int:
        return self._params_count

    def parse_parameters(self, params: Optional[List[str]]) -> Any:
        return self._params_parser(params)


class IntArgParamsParser(ArgParamsParser):
    def required_parameters_count(self) -> int:
        return 1

    def parse_parameters(self, params: Optional[str]) -> Any:
        return to_int(params[0], raise_exceptions=True)


class PresenceArgParamsParser(ArgParamsParser):
    def required_parameters_count(self) -> int:
        return 0

    def parse_parameters(self, _: Optional[List[str]]) -> Any:
        return True


class NoopArgParamsParser(ArgParamsParser):
    def required_parameters_count(self) -> int:
        return ArgParamsParser.VARIADIC_PARAMETERS_COUNT

    def parse_parameters(self, params: Optional[List[str]]) -> Any:
        return params

#
# class IntArgParamsParser(ArgParamsParser):
#     def required_parameters_count(self) -> int:
#         return 0
#
#     def parse_parameters(self, params: Optional[List[str]]) -> Any:
#         return [to_int(p, raise_exceptions=True) for p in params]


class KwArgSpec:
    def __init__(self,
                 aliases: Union[str, List[str]],
                 params_parser: ArgParamsParser):

        self.aliases: List[str] = list_wrap(aliases)
        self.params_parser: ArgParamsParser = params_parser


class Args:
    def __init__(self, parsed: Dict, unparsed: List[Any] = None):
        self._parsed = parsed
        self._unparsed = unparsed

    def __str__(self):
        return json_to_pretty_str({
            "parsed": self._parsed,
            "unparsed": self._unparsed
        })

    def __contains__(self, item):
        return self.has_kwarg(item)

    # Positional arguments

    def has_vargs(self) -> bool:
        return True if self.get_vargs() is not None else False

    def get_varg(self, default=None) -> Optional[Any]:
        vargs = self.get_vargs()
        if vargs:
            return vargs[0]
        return default

    def get_vargs(self, default=None) -> Optional[List[Any]]:
        return self._parsed.get(None, default)

    # Keyword arguments

    def has_kwarg(self, aliases: Union[str, List[str]]) -> bool:
        return True if self.get_kwarg_params(aliases) is not None else None

    def get_kwarg_param(self, aliases: Union[str, List[str]], default=None) -> Optional[Any]:
        params = self.get_kwarg_params(aliases)
        if params:
            return params[0]
        return default

    def get_kwarg_params(self, aliases: Union[str, List[str]], default=None) -> Optional[List[Any]]:
        for alias in list_wrap(aliases):
            if alias in self._parsed:
                return self._parsed.get(alias)

        return default

    def get_unparsed_args(self, default=None) -> Optional[List[str]]:
        return self._unparsed or default

    @staticmethod
    def parse(args: List[str], *,
              kwargs_specs: List[KwArgSpec] = None,
              vargs_parser: ArgParamsParser = NoopArgParamsParser(),
              continue_parsing_hook: Optional[Callable[[str, int, 'Args'], bool]] = None) -> Optional['Args']:

        kwargs_specs = kwargs_specs or []
        parsed = {}
        unparsed = []
        positionals = []

        ret = Args(parsed, unparsed)
        cursor = 0

        def get_bucket(kw_arg_name: str) -> Tuple[Optional[List], Optional[KwArgSpec]]:
            nonlocal parsed

            log.d("get_bucket (%s)", kw_arg_name)

            for arg_spec in kwargs_specs:
                if kw_arg_name in arg_spec.aliases:

                    # Found an alias that matches the argument name
                    log.i("%s", kw_arg_name)

                    # Check whether this argument was already found,
                    # if not allocate a new list using this arg_name
                    # Check for every alias
                    bck = None
                    for a_arg_alias in arg_spec.aliases:
                        if a_arg_alias in parsed:
                            bck = parsed.get(a_arg_alias)
                            break

                    # If bucket is still None, then we have to allocate it
                    if not bck:
                        bck = []
                        parsed[kw_arg_name] = bck

                    log.d("Returning bucket for %s", kw_arg_name)

                    return bck, arg_spec

            return None, None

        def append_to_bucket(bucket: List[str],
                             params_parser: ArgParamsParser,
                             param_ok_hook: Callable[[str], bool] = lambda: True):
            nonlocal cursor
            nonlocal args

            # Ensure that we have enough params to provide
            # to the params parser of this argument
            required_params_count = params_parser.required_parameters_count()
            log.d("Arg '%s' requires %d params", args[cursor], required_params_count)

            if required_params_count == ArgParamsParser.VARIADIC_PARAMETERS_COUNT:
                raise Exception("Variadic arguments for kwarg not implemented")

            if cursor + required_params_count >= len(args):
                log.e("Not enough parameters to feed argument '%s'", args[cursor])
                raise IndexError("not enough parameters to feed argument")

            # Ensure that the params are allowed
            # (the check could be performed even by the params_parser; this
            # is just an helper, for example for filter kwarg/varg)

            param_offset = 0

            while param_offset < required_params_count:
                param = args[cursor + 1 + param_offset]
                log.d("Checking validity: param_ok_hook('%s')", param)
                if not param_ok_hook(param):
                    log.e("Invalid parameter for feed '%s'", args[cursor])
                    raise ValueError("not enough parameters to feed argument")

                param_offset += 1

            log.d("Parsing and appending to bucket")

            # Provide the params to the parser, and add
            # the parsed value to the bucket
            val = params_parser.parse_parameters(
                args[(cursor + 1):(cursor + 1 + required_params_count)]
            )

            log.i("> %s", "{}".format(val))
            bucket += list_wrap(val)

            cursor += required_params_count

        log.i("Parsing arguments: %s", args)

        try:
            cursor = 0
            while cursor < len(args):
                arg = args[cursor]

                log.d("Inspecting argument %s", arg)

                # Check whether we can go further

                if continue_parsing_hook:
                    cont = continue_parsing_hook(arg, cursor, ret)
                    log.d("continue: %d", cont)

                    if not cont:
                        log.i("Parsed stopped by the continue hook")
                        # Add the remaining args as positional arguments
                        unparsed += args[cursor:]
                        log.d("Unparsed args: %s", unparsed)

                        return ret

                # The hook didn't block us, go on

                # Check whether this is a kwarg or varg

                if _is_long_kwarg(arg):
                    # Long format kwarg

                    arg_name = arg

                    # Check whether this is a known argument
                    bucket, argpec = get_bucket(arg_name)

                    if bucket is not None:
                        append_to_bucket(bucket,
                                         params_parser=argpec.params_parser,
                                         param_ok_hook=lambda p: not _is_kwarg)
                    else:
                        log.w("Unknown argument: '%s'", arg_name)

                elif arg.startswith("-") and len(arg) > 1:
                    # Short format kwarg
                    # e.g. "-v"
                    # e.g. "-lsh"

                    # Allow concatenation of arguments (as letters)
                    args_chain = unprefix(arg, "-")     # e.g "lsh"
                    chain_idx = 0

                    while chain_idx < len(args_chain):
                        c_arg_name = "-" + args_chain[chain_idx]
                        is_last_of_chain = chain_idx == len(args_chain) - 1
                        # e.g "-l"
                        # e.g "-s"
                        # e.g "-h"

                        # Check whether this is a known argument
                        bucket, argpec = get_bucket(c_arg_name)
                        if bucket is not None:
                            # We can feed the parser only if we are on the
                            # last param of the chain, otherwise params_count
                            # must be 0
                            append_to_bucket(bucket,
                                             params_parser=argpec.params_parser,
                                             param_ok_hook=lambda s: not _is_kwarg(s) and is_last_of_chain)
                        else:
                            log.w("Unknown argument in chain: '%s'", c_arg_name)

                        chain_idx += 1

                else:
                    # Positional varg
                    log.d("Considering '%s' as positional parameter", arg)
                    # Add as it is (non parsed) for now, will parse all the vargs
                    # at the end
                    positionals.append(arg)

                cursor += 1

            bucket = parsed.setdefault(None, [])

            pos_params_count = vargs_parser.required_parameters_count()
            if pos_params_count != ArgParamsParser.VARIADIC_PARAMETERS_COUNT:
                # We need a constant number of parameters, check if we have enough
                if len(positionals) < pos_params_count:
                    log.e("Found %d out of %d positional parameters",
                          len(positionals), pos_params_count)
                    raise Exception("Not enough positional parameters")

                # Parse a subset of positionals and add the remaining to unparsed
                log.d("Parsing (%d) positional parameters: %s",
                      pos_params_count,
                      positionals)
                bucket += list_wrap(vargs_parser.parse_parameters(
                    positionals[:pos_params_count])
                )
                unparsed += positionals[pos_params_count:]
            else:
                # Parse all positionals
                log.d("Parsing (%d*) positional parameters: %s",
                      len(positionals),
                      positionals)
                bucket += list_wrap(vargs_parser.parse_parameters(
                    positionals)
                )

        except Exception as ex:
            log.e("Exception occurred while parsing: %s", ex)
            return None

        return ret


def _is_kwarg(s: str):
    return s.startswith("-") and len(s) > 1


def _is_long_kwarg(s: str):
    return s.startswith("--") and len(s) > 2


def _is_varg(s: str):
    return not _is_kwarg(s)


PARAM_INT = IntArgParamsParser()
PARAM_PRESENCE = PresenceArgParamsParser()


if __name__ == "__main__":
    def main():
        args = Args.parse(
            args=["-v", "5", "randomstring", "--trace", "-p", "6666"],
            args_specs=[
                KwArgSpec(aliases=["-v", "--verbose"], params_parser=PARAM_INT),
                KwArgSpec(aliases=["-t", "--trace"], params_parser=PARAM_PRESENCE),
                KwArgSpec(aliases=["-r", "--reverse"], params_parser=PARAM_PRESENCE),
                KwArgSpec(aliases=["-g", "--group"], params_parser=PARAM_PRESENCE),
                KwArgSpec(aliases=["-l", "--long"], params_parser=PARAM_PRESENCE),
                KwArgSpec(aliases=["-p", "--port"], params_parser=PARAM_INT)
            ]
        )

        if args:
            print(args)

            print(args.get_kwarg_param("-v"))
            print(args.get_kwarg_param(["-t", "--trace"]))
            print(args.has_vargs())
            print(args.get_vargs())

    main()