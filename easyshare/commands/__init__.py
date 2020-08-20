from abc import ABC, abstractmethod
from typing import Optional, List


class CommandOptionInfo:
    """ Provide information of an option (aliases, parameter, description) """
    def __init__(self,
                 aliases: Optional[List[str]],
                 description: str,
                 params: Optional[List[str]] = None):
        self.aliases = aliases
        self.description = description
        self.params = params

    def aliases_str(self) -> str:
        """
        Returns comma separated aliases, e.g. "-c, --config"
        """
        if not self.aliases:
            return ''
        return ', '.join(self.aliases)

    def params_str(self) -> str:
        """
        Returns space separated params, e.g. "param1 param2"
        """
        if not self.params:
            return ''
        return ' '.join(self.params)

    def to_str(self, justification: int = 0) -> str:
        """
        Returns aliases_string() + params_string() (justified by the given amount)
        + description
        """
        return CommandOptionInfo.as_string(
            self.aliases_str(),
            self.params_str(),
            self.description,
            justification
        )

    @staticmethod
    def as_string(aliases: str, params: str, description: str, justification: int) -> str:
        return f"{(aliases + ('  ' if params else '') + params).ljust(justification)}{description}"


class CommandUsage(ABC):
    """ Provide minimal information of a command (name, synopsis, options) """
    @classmethod
    @abstractmethod
    def name(cls) -> str:
        # e.g. ls
        pass

    @classmethod
    @abstractmethod
    def synopsis(cls) -> str:
        # e.g. ls [OPTION]... [DIR]
        pass

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        # e.g. [("-c", "--config", "config file"), ...]
        return []

    @classmethod
    def see_also(cls) -> Optional[str]:
        return None


class CommandHelp(CommandUsage):
    """ Provide full information of a command, ideal for a man page """

    @classmethod
    @abstractmethod
    def short_description(cls) -> str:
        # e.g. list local directory contents in a tree-like format
        pass

    @classmethod
    @abstractmethod
    def long_description(cls) -> str:
        # Description section
        pass

    @classmethod
    def examples(cls) -> Optional[str]:
        # Example section
        return None

    @classmethod
    def custom(cls) -> Optional[str]:
        """
        Override for treat this as a custom command for which the other
        fields don't make sense (e.g. an alias)
        """
        return None