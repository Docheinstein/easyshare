import copy

from abc import ABC
from enum import Enum
from typing import List, Any, Optional, Union, Tuple, Callable, Dict

from easyshare.logging import get_logger
from easyshare.utils.json import j
from easyshare.utils.str import unprefix
from easyshare.utils.types import to_int, list_wrap

log = get_logger(__name__)


# --- Conventions ---
# Arguments
#   all the arguments
#   e.g. "-p port -c config operand1 operand2"
# Option
#   all the arguments beginning with - (and --)
#   e.g. -p             // -p
# Option aliases
#   the names of the options
#   e.g. -p, --port
# Option parameter
#   a parameter of an option
#   e.g. -p port        // port
# Positionals
#   the operands (neither option nor option's parameter)
#   e.g. ls -l /tmp     // /tmp

class ArgsParseError(Exception):
    pass


class OptionParams(ABC):
    """
    Params of an option (e.g. -p port => port).
    Contains info about parameters count and provide the parser
    for the parameters.
    """
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
            "*" if self.optional_count == OptionParams.VARIADIC_PARAMETERS_COUNT else self.optional_count
        )

# aliases, params
Option = Tuple[Union[str, List[str]], OptionParams]


class ArgType(Enum):
    OPTION = object()
    OPTION_PARAM = object()
    POSITIONAL = object()

class Args:
    def __init__(self, parsed: Dict, unparsed: List[Any] = None):
        unparsed = [] if unparsed is None else unparsed
        self._parsed = parsed
        self._unparsed = unparsed

    def __str__(self):
        return j({
            "parsed": self._parsed,
            "unparsed": self._unparsed
        })

    def __contains__(self, item):
        return self.has_option(item)

    @staticmethod
    def parse(args: List[str], *,
              positionals_spec: OptionParams = None,
              options_spec: List[Option] = None,
              continue_parsing_hook: Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]] = None):
        return ArgsParser(args,
                          positionals_spec=positionals_spec,
                          options_spec=options_spec,
                          continue_parsing_hook=continue_parsing_hook).parse()

    # === POSITIONALS ===

    def has_positionals(self) -> bool:
        """ Returns whether there are positionals arguments """
        return True if self.get_positionals() is not None else False

    def get_positional(self, default=None) -> Optional[Any]:
        pargs = self.get_positionals()
        if pargs:
            return pargs[0]
        return default

    def get_positionals(self, default=None) -> Optional[List[Any]]:
        """ Returns all the positionals, or 'default' if there are not positionals. """
        return self._parsed.get(None, default)

    # === OPTIONS ===

    def has_option(self, aliases: Union[str, List[str]]) -> bool:
        """ Returns whether an option for the given 'aliases' has been found """
        return True if self.get_option_params(aliases) is not None else None

    def option_has_param(self, aliases: Union[str, List[str]]) -> bool:
        """
        Returns whether a parameter for the given 'aliases' has been found
        (apart from the option itself)
        """
        return True if self.get_option_params(aliases) else None

    def get_option_param(self, aliases: Union[str, List[str]], default=None) -> Optional[Any]:
        """ Returns the first parameter of the option for the given 'aliases' """
        params = self.get_option_params(aliases)
        if params:
            return params[0]
        return default

    def get_option_params(self, aliases: Union[str, List[str]], default=None) -> Optional[List[Any]]:
        """ Returns the parameters of the option for the given 'aliases' """
        for alias in list_wrap(aliases):
            if alias in self._parsed:
                return self._parsed.get(alias)

        return default

    def get_unparsed_args(self, default=None) -> Optional[List[str]]:
        """
        Returns the unparsed args
         (there will be unparsed args only if
         continue_parsing_hook stopped the parsing)
        """
        return self._unparsed or default

    def clone(self) -> 'Args':
        return Args(
            parsed=copy.deepcopy(self._parsed),
            unparsed=copy.deepcopy(self._unparsed),
        )


class ArgsParser:

    def __init__(self,
                 args: List[str], *,
                 positionals_spec: OptionParams = None,
                 options_spec: List[Option] = None,
                 continue_parsing_hook: Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]] = None):
        self._args = args
        self._positionals_spec = positionals_spec
        self._options_spec = options_spec
        self._continue_parsing_hook = continue_parsing_hook

        self._positionals_spec = self._positionals_spec or VARIADIC_PARAMS
        self._options_spec  = self._options_spec or []

        self._parsed = {}
        self._unparsed = []
        self._positionals = []
        self._cursor = 0


    def parse(self) -> Args:
        """
                Parses the given arguments using the 'positionals_spec' and 'options_spec'
                for parse positionals and options properly.
                The 'continue_parsing_hook' is a call that can be used for interrupt
                the parsing, by returning False
                """
        log.d("Starting arguments parsing")
        log.d("Known options: %s", [o[0] for o in self._options_spec])

        # For keep idempotent
        self._cursor = 0
        self._parsed = {}
        self._unparsed = []
        self._positionals = []

        ret = Args(self._parsed, self._unparsed)

        try:
            while self._cursor < len(self._args):
                arg = self._args[self._cursor]

                log.d("Inspecting argument %s", arg)

                # Check whether we can go further
                if ArgsParser._is_option(arg):
                    argtype = ArgType.OPTION
                else:
                    argtype = ArgType.POSITIONAL

                if self._continue_parsing_hook:
                    cont = self._continue_parsing_hook(arg, argtype, self._cursor, ret, self._positionals)
                    log.d("continue: %s", cont)

                    if not cont:
                        log.i("Parsed stopped by the continue hook")
                        # Add the remaining args as positional arguments
                        self._unparsed += self._args[self._cursor:]
                        break

                # The hook didn't block us, go on

                # Check whether this is an option or a positional

                if ArgsParser._is_long_option(arg):
                    # Long option
                    # e.g. --config
                    self._handle_option(arg, lambda p: not ArgsParser._is_short_option(p))

                elif ArgsParser._is_short_option(arg):
                    # Short format

                    # e.g. "-v"
                    # e.g. "-lsh"

                    # Allow concatenation of options (as letters)
                    opts_chain = unprefix(arg, "-")  # => e.g "lsh"
                    chain_idx = 0

                    while chain_idx < len(opts_chain):
                        c_opt_name = "-" + opts_chain[chain_idx]
                        is_last_of_chain = chain_idx == len(opts_chain) - 1
                        # e.g "-v"
                        # e.g "-l"

                        # We can feed the parser only if we are on the
                        # last param of the chain, otherwise params_count
                        # must be 0
                        self._handle_option(c_opt_name,
                                            lambda s: not ArgsParser._is_short_option(s) and is_last_of_chain)

                        chain_idx += 1
                else:
                    # Positional parg
                    log.d("Considering '%s' as positional parameter", arg)
                    # Add as it is (non parsed) for now,
                    # will parse all the positionals at the end
                    self._positionals.append(arg)

                self._cursor += 1

            # Parse positionals
            log.d("%d unparsed args w/o positional: %s", len(self._unparsed), self._unparsed)
            log.d("%d positional arguments: %s", len(self._positionals), self._positionals)

            # Create the positionals bucket (None), parse the positionals
            # using the positions_spec and add to the bucket
            positionals_bucket: List = self._parsed.setdefault(None, [])
            parsed_positionals_count = ArgsParser._append_to_bucket(
                positionals_bucket,
                params=self._positionals,
                params_spec=self._positionals_spec,
            )

            if parsed_positionals_count != len(self._positionals):
                log.w("There will be %d unparsed positionals arguments",
                      len(self._positionals) - parsed_positionals_count)

            # Eventually add the remaining to the unparsed
            self._unparsed += self._positionals[parsed_positionals_count:]
            log.d("%d unparsed args: %s", len(self._unparsed), self._unparsed)
            return ret

        except Exception as err:
            raise ArgsParseError(str(err))


    def _get_option_bucket(self, opt_alias: str) -> Tuple[Optional[List], Optional[Option]]:
        """
        Returns the bucket (list of parsed parameters)
        associated with an option alias in 'opt_alias'
        """

        log.d("get_bucket (%s)", opt_alias)

        for option_spec in self._options_spec:
            opt_aliases, opt_params = option_spec
            log.d("Inspecting aliases: %s", opt_aliases)
            if opt_alias in opt_aliases:

                # Found an alias that matches the argument name
                log.i("%s", opt_alias)

                # Check whether this option was already found,
                # if not, allocate a new list using this opt_alias
                # Check for every alias
                bck = None
                for a_opt_alias in opt_aliases:
                    if a_opt_alias in self._parsed:
                        bck = self._parsed.get(a_opt_alias)
                        break

                # If bucket is still None, then we have to allocate it
                if not bck:
                    bck = []
                    self._parsed[opt_alias] = bck

                log.d("Returning bucket for %s", opt_alias)

                return bck, option_spec

        return None, None

    def _handle_option(
            self,
            opt_alias: str,
            param_ok_hook: Callable[[str], bool]) -> bool:
        """
        Treats the argument pointed by cursor as an options, retrieves
        the bucket for it and parses its parameters.
        """

        # Check whether this is a known option
        bucket, opt_spec = self._get_option_bucket(opt_alias)
        if bucket is not None:
            self._cursor += ArgsParser._append_to_bucket(
                bucket,
                params=self._args,
                params_offset=self._cursor + 1,
                params_spec=opt_spec[1],
                param_ok_hook=param_ok_hook)
            return True

        log.w("Unknown argument: '%s'", opt_alias)
        return False

    @staticmethod
    def _append_to_bucket(
            bucket: List,
            params: List[str],
            params_spec: OptionParams,
            params_offset: int = 0,
            param_ok_hook: Callable[[str], bool] = lambda p: True):
        """
        Parses 'params' following the 'params_spec' rules and inserts
        those into the bucket (list of parsed parameters).
        The 'params_offset' can be used for start the look from that index.
        The 'param_ok_hook' can be used for interrupt the parsing process
        at a certain point for some reason (e.g. don't consider an argument
        as an option parameter for variadic params if it is an option starting with -)
        """
        log.d("Parsing and appending to bucket...\n"
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

        while params_spec.optional_count == OptionParams.VARIADIC_PARAMETERS_COUNT \
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

        except:
            log.w("Exception occurred while parsing optional argument; "
                  "considering it as a different argument")

            return pre_optionals_param_cursor

        return param_cursor

    @staticmethod
    def _is_short_option(s: str):
        """ Returns whether s is an option (starts with -) and is not a negative number)"""
        if not s.startswith("-") or len(s) <= 1:
            return False
        # Might be a negative number...
        try:
            to_int(s[1:], raise_exceptions=True)
            return False # is a negative number
        except ValueError:
            return True


    @staticmethod
    def _is_long_option(s: str):
        """ Returns whether s is a long option (starts with --) """
        return s.startswith("--") and len(s) > 2

    @staticmethod
    def _is_option(s: str):
        return ArgsParser._is_short_option(s) or ArgsParser._is_long_option(s)

    @staticmethod
    def _is_positional(s: str):
        """ Returns whether s is a positional argument (not an option) """
        return not ArgsParser._is_option(s)

# =============================================
# ============ ParamsSpec HELPERS =============
# =============================================

class IntParams(OptionParams):
    def __init__(self, mandatory_count: int, optional_count: int = 0):
        super().__init__(mandatory_count, optional_count,
                         lambda ps: [to_int(p, raise_exceptions=True) for p in ps])


class StrParams(OptionParams):
    def __init__(self, mandatory_count: int, optional_count: int = 0):
        super().__init__(mandatory_count, optional_count,
                         lambda ps: ps)


STR_PARAM = StrParams(1, 0)
STR_PARAM_OPT = StrParams(0, 1)

INT_PARAM = IntParams(1, 0)
INT_PARAM_OPT = IntParams(0, 1)

PRESENCE_PARAM = OptionParams(0, 0, lambda ps: True)

VARIADIC_PARAMS = StrParams(0, OptionParams.VARIADIC_PARAMETERS_COUNT)

# =============================================
# ============ ArgsParser HELPERS =============
# =============================================

class ArgsSpec:
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            positionals_spec=self.positionals_spec(),
            options_spec=self.options_spec(),
            continue_parsing_hook=self.continue_parsing_hook(),
        )

    def positionals_spec(self) -> Optional[OptionParams]:
        return None

    def options_spec(self) -> Optional[List[Option]]:
        return None

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
        return None


class PosArgsSpec(ArgsSpec):
    def __init__(self, mandatory: int, optional: int = 0):
        self.mandatory = mandatory
        self.optional = optional

    def positionals_spec(self) -> Optional[OptionParams]:
        return StrParams(self.mandatory, self.optional)

class VarArgsSpec(PosArgsSpec):
    def __init__(self, mandatory: int = 0):
        super().__init__(mandatory, OptionParams.VARIADIC_PARAMETERS_COUNT)


class NoPosArgsSpec(PosArgsSpec):
    def __init__(self):
        super().__init__(0, 0)


class IntPosArgSpec(ArgsSpec):
    def positionals_spec(self) -> Optional[OptionParams]:
        return INT_PARAM


class OptIntPosArgSpec(ArgsSpec):
    def positionals_spec(self) -> Optional[OptionParams]:
        return INT_PARAM_OPT


class StopParseArgsSpec(ArgsSpec):
    def __init__(self, mandatory: int = 0, stop_after: int = None):
        self.mandatory = mandatory
        self.stop_after = stop_after or mandatory

    def positionals_spec(self) -> Optional[OptionParams]:
        return StrParams(self.mandatory, 0)

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgsSpec, int, 'Args', List[str]], bool]]:
        return lambda arg, argtype, idx, parsedargs, positionals: len(positionals) < self.stop_after