from abc import abstractmethod, ABC
from typing import List, Optional

from easyshare.args import ParamsSpec, INT_PARAM, Args, NoopParamsSpec, OPT_INT_PARAM


class ArgsParser(ABC):
    @abstractmethod
    def parse(self, args: List[str]) -> Optional[Args]:
        pass


class VariadicArgs(ArgsParser):
    def __init__(self, mandatory: int = 0):
        self.mandatory = mandatory

    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            vargs_spec=NoopParamsSpec(self.mandatory, ParamsSpec.VARIADIC_PARAMETERS_COUNT)
        )


class PositionalArgs(ArgsParser):
    def __init__(self, mandatory: int, optional: int = 0):
        self.mandatory = mandatory
        self.optional = optional

    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            vargs_spec=NoopParamsSpec(self.mandatory, self.optional)
        )


class IntArg(ArgsParser):
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            vargs_spec=INT_PARAM
        )


class OptIntArg(ArgsParser):
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            vargs_spec=OPT_INT_PARAM
        )


class NoParseArgs(ArgsParser):
    def parse(self, args: List[str]) -> Optional[Args]:
        return Args.parse(
            args=args,
            continue_parsing_hook=lambda arg, idx, parsedargs, positionals: False
        )
