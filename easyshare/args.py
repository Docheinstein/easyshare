from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Any, Optional, Union, Tuple, Callable, Dict

from easyshare.logging import get_logger
from easyshare.utils.json import j
from easyshare.utils.str import unprefix
from easyshare.utils.types import to_int, list_wrap, is_int

log = get_logger(__name__)


class ArgsParseError(Exception):
    pass


class Params(ABC):
    VARIADIC_PARAMETERS_COUNT = -1

    def __init__(self,
                 mandatory_count: int,
                 optional_count: int,
                 parser: Callable[[List[str]], Any]):
        self.mandatory_count = mandatory_count
        self.optional_count = optional_count
        self.parser = parser

    def __str__(self):
        return "{} : {} mandatory, {} optional".format(
            self.__class__.__name__,
            self.mandatory_count,
            "*" if self.optional_count == Params.VARIADIC_PARAMETERS_COUNT else self.optional_count
        )

# aliases, params_spec
Kwarg = Tuple[Union[str, List[str]], Params]

# class KwArgSpec:
#     def __init__(self,
#                  aliases: Union[str, List[str]],
#                  params_spec: ParamsSpec):
#
#         self.aliases: List[str] = list_wrap(aliases)
#         self.params_spec: ParamsSpec = params_spec


class ArgType(Enum):
    KWARG = object()
    KWARG_PARAM = object()
    PARG = object()


class Args:
    def __init__(self, parsed: Dict, unparsed: List[Any] = None):
        self._parsed = parsed
        self._unparsed = unparsed

    def __str__(self):
        return j({
            "parsed": self._parsed,
            "unparsed": self._unparsed
        })

    def __contains__(self, item):
        return self.has_kwarg(item)

    # Positional arguments

    def has_pargs(self) -> bool:
        return True if self.get_pargs() is not None else False

    def get_parg(self, default=None) -> Optional[Any]:
        pargs = self.get_pargs()
        if pargs:
            return pargs[0]
        return default

    def get_pargs(self, default=None) -> Optional[List[Any]]:
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
              pargs_spec: Params = None,
              kwargs_specs: List[Kwarg] = None,
              continue_parsing_hook: Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]] = None) -> 'Args':
            # continue_parsing_hook: argname, argtype, idx, args, positionals

        pargs_spec = pargs_spec or VARIADIC_PARAMS
        kwargs_specs = kwargs_specs or []
        parsed = {}
        unparsed = []
        positionals = []

        ret = Args(parsed, unparsed)

        def get_bucket(kw_arg_name: str) -> Tuple[Optional[List], Optional[Kwarg]]:
            nonlocal parsed

            log.d("get_bucket (%s)", kw_arg_name)

            for arg_spec in kwargs_specs:
                arg_spec_aliases, arg_spec_param_spec = arg_spec

                if kw_arg_name in arg_spec_aliases:

                    # Found an alias that matches the argument name
                    log.i("%s", kw_arg_name)

                    # Check whether this argument was already found,
                    # if not allocate a new list using this arg_name
                    # Check for every alias
                    bck = None
                    for a_arg_alias in arg_spec_aliases:
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

        try:
            cursor = 0
            while cursor < len(args):
                arg = args[cursor]

                log.d("Inspecting argument %s", arg)

                # Check whether we can go further
                if Args._is_long_kwarg(arg) or Args._is_kwarg(arg):
                    argtype = ArgType.KWARG
                else:
                    argtype = ArgType.PARG

                if continue_parsing_hook:
                    cont = continue_parsing_hook(arg, argtype, cursor, ret, positionals)
                    log.d("continue: %s", cont)

                    if not cont:
                        log.i("Parsed stopped by the continue hook")
                        # Add the remaining args as positional arguments
                        unparsed += args[cursor:]
                        log.d("Unparsed args: %s", unparsed)

                        break

                # The hook didn't block us, go on

                # Check whether this is a kwarg or parg

                if Args._is_long_kwarg(arg):
                    # Long format kwarg

                    bucket, kwargspec = get_bucket(arg)

                    if bucket is not None:
                        cursor += Args._append_to_bucket(
                            bucket,
                            params=args,
                            params_offset=cursor + 1,
                            params_spec=kwargspec[1],
                            param_ok_hook=lambda p: not Args._is_kwarg(p))
                    else:
                        log.w("Unknown argument: '%s'", arg)

                elif Args._is_kwarg(arg):
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
                        bucket, kwargspec = get_bucket(c_arg_name)
                        if bucket is not None:
                            # We can feed the parser only if we are on the
                            # last param of the chain, otherwise params_count
                            # must be 0
                            cursor += Args._append_to_bucket(
                                bucket,
                                params=args,
                                params_offset=cursor + 1,
                                params_spec=kwargspec[1],
                                param_ok_hook=lambda s: not Args._is_kwarg(s) and is_last_of_chain)
                        else:
                            log.w("Unknown argument in chain: '%s'", c_arg_name)

                        chain_idx += 1

                else:
                    # Positional parg
                    log.d("Considering '%s' as positional parameter", arg)
                    # Add as it is (non parsed) for now, will parse all the pargs
                    # at the end
                    positionals.append(arg)

                cursor += 1

            # Parse positionals
            log.d("%d positional arguments", len(positionals))

            positionals_bucket = parsed.setdefault(None, [])
            positionals_count = Args._append_to_bucket(
                positionals_bucket,
                params=positionals,
                params_spec=pargs_spec,
            )

            if positionals_count != len(positionals):
                log.w("There will be %d unparsed positionals arguments",
                      len(positionals) - positionals_count)

            # Eventually add the remaining to the unparsed
            unparsed += positionals[positionals_count:]

            return ret

        except Exception as err:
            raise ArgsParseError(str(err))



    @staticmethod
    def _is_kwarg(s: str):
        if not s.startswith("-") or len(s) <= 1:
            return False
        # Might be a negative number...
        try:
            to_int(s[1:], raise_exceptions=True)
            return False # is a negative number
        except Exception:
            return True


    @staticmethod
    def _is_long_kwarg(s: str):
        return s.startswith("--") and len(s) > 2


    @staticmethod
    def _is_parg(s: str):
        return not Args._is_kwarg(s)


    @staticmethod
    def _append_to_bucket(bucket: List[str],
                          params: List[str],
                          params_spec: Params,
                          params_offset: int = 0,
                          param_ok_hook: Callable[[str], bool] = lambda p: True):

        log.d("Parsing and append to bucket...\n"
              "\t%s\n"
              "\tparams = %s\n"
              "\toffset = %d",
              str(params_spec), params, params_offset)

        param_cursor = 0

        # MANDATORY

        # Ensure that we have enough params to provide
        # to the params parser of this argument

        if params_offset + params_spec.mandatory_count > len(params):
            raise IndexError("not enough parameters to feed argument")

        # Ensure that the params are allowed
        # (the check could be performed even by the params_parser; this
        # is just an helper, for example for filter kwarg/parg)

        while param_cursor < params_spec.mandatory_count:
            param = params[params_offset + param_cursor]
            log.d("[%d] Mandatory: checking validity: param_ok_hook('%s')", param_cursor, param)

            if not param_ok_hook(param):
                raise ValueError("invalid parameter for feed argument '{}'".format(param))

            param_cursor += 1


        # Remind were we are, for treat optionals parsing errors
        pre_optionals_param_cursor = param_cursor

        # OPTIONALS

        while params_spec.optional_count == Params.VARIADIC_PARAMETERS_COUNT \
                or param_cursor < params_spec.mandatory_count + params_spec.optional_count:

            # Check if it is there
            if params_offset + param_cursor < len(params):
                # There is this optional param, check if is valid
                param = params[params_offset + param_cursor]
                log.d("[%d] Optional: checking validity: param_ok_hook('%s')", param_cursor, param)

                if not param_ok_hook(param):
                    log.d("Optional parameter not found; no problem")
                    break
            else:
                log.d("No more params, stopping optionals fetching")
                break

            param_cursor += 1

        log.d("Parsing and appending to bucket (taking %d:%d)",
              params_offset, params_offset + param_cursor)

        # Provide the params to the parser, and add
        # the parsed value to the bucket
        try:
            val = params_spec.parser(
                params[params_offset:params_offset + param_cursor]
            )
            log.i("> %s", "{}".format(val))
            bucket += list_wrap(val)

        except Exception:
            log.w("Exception occurred while parsing optional argument; "
                  "considering it as a differnt argument")

            return pre_optionals_param_cursor


        return param_cursor


# =============================================
# ============ ParamsSpec HELPERS =============
# =============================================

class IntParams(Params):
    def __init__(self, mandatory_count: int, optional_count: int = 0):
        super().__init__(mandatory_count, optional_count,
                         lambda ps: [to_int(p, raise_exceptions=True) for p in ps])


class NoopParams(Params):
    def __init__(self, mandatory_count: int, optional_count: int = 0):
        super().__init__(mandatory_count, optional_count,
                         lambda ps: ps)

class ActionParam(Params):
    def __init__(self, action: Callable[[List[str]], Any]):
        super().__init__(0, 0, action)


STR_PARAM = NoopParams(1, 0)
STR_PARAM_OPT = NoopParams(0, 1)

INT_PARAM = IntParams(1, 0)
INT_PARAM_OPT = IntParams(0, 1)

PRESENCE_PARAM = Params(0, 0, lambda ps: True)

VARIADIC_PARAMS = NoopParams(0, Params.VARIADIC_PARAMETERS_COUNT)

# =============================================
# ============ ArgsParser HELPERS =============
# =============================================

class ArgsParser:
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            pargs_spec=self.pargs_spec(),
            kwargs_specs=self.kwargs_specs(),
            continue_parsing_hook=self.continue_parsing_hook(),
        )

    def pargs_spec(self) -> Optional[Params]:
        return None

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return None

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
        return None


class Pargs(ArgsParser):
    def __init__(self, mandatory: int, optional: int = 0):
        self.mandatory = mandatory
        self.optional = optional

    def pargs_spec(self) -> Optional[Params]:
        return NoopParams(self.mandatory, self.optional)

class VariadicPargs(Pargs):
    def __init__(self, mandatory: int = 0):
        super().__init__(mandatory, Params.VARIADIC_PARAMETERS_COUNT)


class NoPargs(Pargs):
    def __init__(self):
        super().__init__(0, 0)


class IntParg(ArgsParser):
    def pargs_spec(self) -> Optional[Params]:
        return INT_PARAM


class OptIntArg(ArgsParser):
    def pargs_spec(self) -> Optional[Params]:
        return INT_PARAM_OPT


class StopParseArgs(ArgsParser):
    def __init__(self, mandatory: int = 0, stop_after: int = None):
        self.mandatory = mandatory
        self.stop_after = stop_after or mandatory

    def pargs_spec(self) -> Optional[Params]:
        return NoopParams(self.mandatory, 0)

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
        return lambda arg, argtype, idx, parsedargs, positionals: len(positionals) < self.stop_after

# if __name__ == "__main__":
#     def main():
#         args = Args.parse(
#             args=["-v", "5", "randomstring", "--trace", "-p", "6666"],
#             args_specs=[
#                 KwArgSpec(aliases=["-v", "--verbose"], params_parser=PARAM_INT),
#                 KwArgSpec(aliases=["-t", "--trace"], params_parser=PARAM_PRESENCE),
#                 KwArgSpec(aliases=["-r", "--reverse"], params_parser=PARAM_PRESENCE),
#                 KwArgSpec(aliases=["-g", "--group"], params_parser=PARAM_PRESENCE),
#                 KwArgSpec(aliases=["-l", "--long"], params_parser=PARAM_PRESENCE),
#                 KwArgSpec(aliases=["-p", "--port"], params_parser=PARAM_INT)
#             ]
#         )
#
#         if args:
#             print(args)
#
#             print(args.get_kwarg_param("-v"))
#             print(args.get_kwarg_param(["-t", "--trace"]))
#             print(args.has_pargs())
#             print(args.get_pargs())
#
#     main()