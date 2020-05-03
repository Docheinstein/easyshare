from typing import List, Optional, Callable

from easyshare.args import ParamsSpec, INT_PARAM, Args, NoopParamsSpec, OPT_INT_PARAM, KwArgSpec


class ArgsParser:
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            vargs_spec=self._vargs_spec(),
            kwargs_specs=self._kwargs_specs(),
            continue_parsing_hook=self._continue_parsing_hook(),
        )

    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return None

    def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
        return None

    def _continue_parsing_hook(self) -> Optional[Callable[[str, int, 'Args', List[str]], bool]]:
        return None


class VariadicArgs(ArgsParser):
    def __init__(self, mandatory: int = 0):
        self.mandatory = mandatory

    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return NoopParamsSpec(self.mandatory, ParamsSpec.VARIADIC_PARAMETERS_COUNT)


class PositionalArgs(ArgsParser):
    def __init__(self, mandatory: int, optional: int = 0):
        self.mandatory = mandatory
        self.optional = optional

    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return NoopParamsSpec(self.mandatory, self.optional)


class IntArg(ArgsParser):
    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return INT_PARAM


class OptIntArg(ArgsParser):
    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return OPT_INT_PARAM


class StopParseArgs(ArgsParser):
    def __init__(self, mandatory: int = 0, stop_after: int = 0):
        self.mandatory = mandatory
        self.stop_after = stop_after

    def _vargs_spec(self) -> Optional[ParamsSpec]:
        return NoopParamsSpec(self.mandatory, 0)

    def _continue_parsing_hook(self) -> Optional[Callable[[str, int, 'Args', List[str]], bool]]:
        return lambda arg, idx, parsedargs, positionals: len(positionals) < self.stop_after
