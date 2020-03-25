import logging
from typing import List, Optional


class Args:
    def __init__(self, args: List[str]):
        self._args = {}
        self._parse(args)

    def __str__(self):
        return str(self._args)

    def has_arg(self, arg_names: List[str]) -> bool:
        """
        Return whether the argument whose name matches one of the
        specified arg_names exists within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: whether the argument exists
        """
        return True if self.get_params(arg_names) is not None else False

    def get_param(self, arg_names: List[str]) -> Optional[str]:
        """
        Returns the first parameter of the argument whose name matches one
        of the specified arg_names, or None if the argument does not exists
        within the parsed arguments.
        None is returned if the argument exists but has not params.
        (i.e. it cannot be possible to distinguish the two cases).
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: the first parameter of the argument
        """
        params = self.get_params(arg_names)
        if not params:
            return None
        return params[0]

    def get_params(self, arg_names: List[str]) -> Optional[List[str]]:
        """
        Returns the parameters of the argument whose name matches one
        of the specified arg_names or None if the argument does not exists
        within the parsed arguments.
        An empty list is returned if the argument exists but has no params.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: the parameters of the argument
        """
        for arg, params in self._args.items():
            for arg_name in arg_names:
                if arg == arg_name:
                    return params
        return None

    def _parse(self, args: List[str]):
        # REMIND:
        # --port        80
        # ^ arg ^    ^ param ^
        i = 0
        while i < len(args):
            arg = args[i]
            arg_name = None

            if arg.startswith("--"):
                # Long format
                arg_name = arg.split("--")[1]
            elif arg.startswith("-"):
                # Short format: allow concatenation of arguments (as letters)
                arg_name_chain = arg.split("-")[1]
                for c in arg_name_chain:
                    self._args[c] = []
                # The argument which allows params is the last one of the chain
                arg_name = arg_name_chain[len(arg_name_chain) - 1]

            i += 1

            if not arg_name:
                # Unexpected: skip argument
                logging.warning("Skipping argument %s", arg)
                continue

            # Check if the current argument has params
            arg_params = []

            while i < len(args):
                arg_param = args[i]
                if arg_param.startswith("-"):
                    # New argument found (not a param), stop the params parsing
                    break
                # We have a param
                arg_params.append(arg_param)
                i += 1

            # Link the params found with the current argument
            self._args[arg_name] = arg_params
