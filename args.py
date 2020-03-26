import logging
from typing import List, Optional, Dict, Union

from utils import strip_prefix


class Args:
    def __init__(self, args: List[str]):
        self._args: Dict[Union[None, str], List[List[str]]] = {}
        self._parse(args)

    def __str__(self):
        return str(self._args)

    def has_arg(self, arg_names: Optional[List[str]] = None) -> bool:
        """
        Return whether the argument whose name matches one of the
        specified arg_names exists within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: whether the argument exists
        """
        return True if self.get_params(arg_names) is not None else False

    def get_param(self, arg_names: Optional[List[str]] = None) -> Optional[str]:
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
            return params
        return params[0]

    def get_params(self, arg_names: Optional[List[str]] = None) -> Optional[List[str]]:
        """
        Returns the parameters of the argument whose name matches one
        of the specified arg_names or None if the argument does not exists
        within the parsed arguments.
        An empty list is returned if the argument exists but has no params.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: the parameters of the argument
        """
        mparams = self.get_mparams(arg_names)
        if not mparams:
            return mparams
        return mparams[0]

    def get_mparams(self, arg_names: Optional[List[str]] = None) -> Optional[List[List[str]]]:
        """
        Returns the (multiple) parameters lists of the argument whose name matches one
        of the specified arg_names or None if the argument does not exists
        within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: the parameters lists of the argument
        """
        if not arg_names:
            return self._args[None]

        ret = None

        for arg_name in arg_names:
            params_lists = self._args.get(arg_name)
            if not params_lists:
                continue

            for param_list in params_lists:
                if not ret:
                    ret = []
                ret.append(param_list)

        return ret

    def _parse(self, args: List[str]):
        # REMIND:
        # --port        80
        # ^ arg ^    ^ param ^
        i = 0
        while i < len(args):
            arg = args[i]
            arg_name = None

            if arg.startswith("--") and len(arg) > 2:
                # Long format
                arg_name = arg
            elif arg.startswith("-") and len(arg) > 1:
                # Short format: allow concatenation of arguments (as letters)
                arg_name_chain = strip_prefix(arg, "-")
                for c in arg_name_chain[:len(arg_name_chain) - 1]:
                    c_arg_name = "-" + c
                    if c not in self._args:
                        # First time
                        self._args[c_arg_name] = []
                    # Append new empty params list
                    self._args[c_arg_name].append([])
                # The argument which allows params is the last one of the chain
                arg_name = "-" + arg_name_chain[len(arg_name_chain) - 1]

            print("ARG_NAME", arg_name)

            i += 1

            # Check if the current argument has params
            arg_params = []

            while i < len(args):
                arg_param = args[i]
                print("ARG_PARAM", arg_param)
                if arg_param.startswith("-"):
                    # New argument found (not a param), stop the params parsing
                    break
                # We have a param
                arg_params.append(arg_param)
                i += 1

            if arg_name not in self._args:
                self._args[arg_name] = []

            print("ARG_PARAMS", arg_params)

            # Link the params found with the current argument
            self._args[arg_name].append(arg_params)