from abc import ABC, abstractmethod
from typing import Optional, List


class CommandOptionHelp:
    def __init__(self,
                 aliases: Optional[List[str]],
                 description: str,
                 params: Optional[List[str]] = None):
        self.aliases = aliases
        self.description = description
        self.params = params

    def aliases_string(self) -> str:
        if not self.aliases:
            return ''
        return ', '.join(self.aliases)

    def params_string(self) -> str:
        if not self.params:
            return ''
        return ' '.join(self.params)

    def to_string(self, justification: int = 0):
        return CommandOptionHelp._to_string(
            self.aliases_string(),
            self.params_string(),
            self.description,
            justification
        )

    @staticmethod
    def _to_string(aliases: str, params: str, description: str, justification: int):
        return f"{(aliases + ('  ' if params else '') + params).ljust(justification)}{description}"


class CommandHelp(ABC):
    @classmethod
    @abstractmethod
    def name(cls):
        pass

    @classmethod
    @abstractmethod
    def short_description(cls):
        pass

    @classmethod
    @abstractmethod
    def synopsis(cls):
        pass

    @classmethod
    def synopsis_extra(cls):
        return None

    @classmethod
    @abstractmethod
    def long_description(cls):
        pass

    @classmethod
    def options(cls) -> List[CommandOptionHelp]:
        return []

    @classmethod
    def examples(cls):
        return []

    @classmethod
    def see_also(cls):
        return None

    @classmethod
    def custom(cls):
        return None