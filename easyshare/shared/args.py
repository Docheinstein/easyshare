from typing import List, Optional, Dict, Union, Tuple, Any

from easyshare.utils.str import unprefix
from easyshare.utils.types import is_valid_list, is_str


class Args:
    DEBUG = False

    def __init__(self, args: List[str]):
        self._args: Dict[Union[None, str], List[List[str]]] = {}
        self._parse(args)

    def __str__(self):
        return str(self._args)

    def __contains__(self, item):
        if not item:
            return False
        if is_valid_list(item):
            return self.has_arg(item)
        if is_str(item):
            return self.has_arg([item])
        return False

    def has_arg(self, arg_names: Optional[List[str]] = None) -> bool:
        """
        Return whether the argument whose name matches one of the
        specified arg_names exists within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :return: whether the argument exists
        """
        return True if self.get_params(arg_names) is not None else False

    def get_param(self, arg_names: Optional[List[str]] = None,
                  position=0, default=None) -> Optional[str]:
        """
        Returns the parameter at position 'position' of the argument whose name
        matches one of the specified arg_names, or 'default' (None as default) if
        the argument does not exists within the parsed arguments.
        None is returned if the argument exists but has not params.
        (i.e. it cannot be possible to distinguish the two cases).
        :param arg_names: list of possible argument names (e.g. short and long format)
        :param position: the position of the parameter to take from
                         the param list (default 0)
        :param default: default value to return if nothing is found
        :return: the first parameter of the argument
        """
        params, found = self._get_params(arg_names, default=default, tell_found=True)
        if not found or position >= len(params):
            return params
        return params[position]

    def get_params(self, arg_names: Optional[List[str]] = None,
                   default=None) -> Optional[List[str]]:
        """
        Returns the parameters of the argument whose name matches one
        of the specified arg_names or 'default' (None as default) if
        the argument does not exists within the parsed arguments.
        An empty list is returned if the argument exists but has no params.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :param default: default value to return if nothing is found
        :return: the parameters of the argument
        """
        return self._get_params(arg_names, default)

    def get_mparams(self, arg_names: Optional[List[str]] = None,
                     default=None) -> Optional[List[List[str]]]:
        """
        Returns the (multiple) parameters lists of the argument whose name matches one
        of the specified arg_names or 'default' (None as default) if
        the argument does not exists within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :param default: default value to return if nothing is found
        :return: the parameters lists of the argument
        """
        return self._get_mparams(arg_names, default)

    def get_mparams_count(self, arg_names: Optional[List[str]] = None) -> int:
        """
        Returns the number of parameters lists of the argument whose name matches one
        of the specified arg_names (even if the parameters list is empty).
        e.g. -s "first" -s "second"                 returns 2
        e.g. -s "first" -s "second" "second_bis"    returns 2
        e.g. -vvvv                                  returns 4
        :param arg_names:
        :return: the number of parameters lists
        """
        mparams, found = self._get_mparams(arg_names, tell_found=True)
        if not found:
            return 0
        return len(mparams)

    def _get_params(self, arg_names: Optional[List[str]] = None, default=None,
                    tell_found=False) -> Union[Optional[List[str]],
                                               Tuple[Optional[List[str]],
                                                     bool]]:
        """
        Returns the parameters of the argument whose name matches one
        of the specified arg_names or 'default' (None as default) if
        the argument does not exists within the parsed arguments.
        An empty list is returned if the argument exists but has no params.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :param default: default value to return if nothing is found
        :param tell_found: whether return a tuple whose second value is whether
                            the argument has been found
        :return: the parameters of the argument [, found]
        """
        mparams, found = self._get_mparams(arg_names, default=default, tell_found=True)
        if not found or not mparams:
            return Args._wrap_finding(mparams, False, tell_found)

        return Args._wrap_finding(mparams[0], True, tell_found)

    def _get_mparams(self, arg_names: Optional[List[str]] = None, default=None,
                     tell_found=False) -> Union[Optional[List[List[str]]],
                                                Tuple[Optional[List[List[str]]],
                                                      bool]]:
        """
        Returns the (multiple) parameters lists of the argument whose name matches one
        of the specified arg_names or 'default' (None as default) if
        the argument does not exists within the parsed arguments.
        :param arg_names: list of possible argument names (e.g. short and long format)
        :param default: default value to return if nothing is found
        :param tell_found: whether return a tuple whose second value is whether
                            the argument has been found
        :return: the parameters lists of the argument [, found]
        """
        self._debug("tell_found: ", tell_found)

        if not arg_names:
            # None refers to the first parameters without leading '-'
            return Args._wrap_finding(self._args.get(None, default),
                                      True, tell_found)

        ret = None

        self._debug("arg_names: ", arg_names)

        for arg_name in arg_names:
            self._debug("- arg_name: ", arg_name)
            params_lists = self._args.get(arg_name)
            self._debug("- params_lists: ", params_lists)

            if not params_lists:
                continue

            for param_list in params_lists:
                self._debug("-- param_list: ", param_list)
                if not ret:
                    ret = []
                ret.append(param_list)

        if ret is None:
            # Nothing found
            self._debug("Nothing found")
            return Args._wrap_finding(default, False, tell_found)

        return Args._wrap_finding(ret, True, tell_found)

    @staticmethod
    def _wrap_finding(something: Any, found: bool, tell_found: bool):
        """
        Returns 'something' if tell_found is False or ('something', found) otherwise.
        :param something:
        :param found:
        :param tell_found:
        :return: 'something' or ('something', found)
        """
        return something if not tell_found else (something, found)

    def _parse(self, args: List[str]):
        # REMIND:
        # --port        80
        # ^ arg ^    ^ param ^

        self._debug("_parse")

        i = 0
        while i < len(args):
            arg = args[i]
            arg_name = None

            if arg.startswith("--") and len(arg) > 2:
                # Long format
                arg_name = arg
            elif arg.startswith("-") and len(arg) > 1:
                # Short format: allow concatenation of arguments (as letters)
                arg_name_chain = unprefix(arg, "-")
                for c in arg_name_chain[:len(arg_name_chain) - 1]:
                    c_arg_name = "-" + c
                    if c_arg_name not in self._args:
                        # First time
                        self._args[c_arg_name] = []

                    self._debug(c_arg_name)

                    # Append new empty params list
                    self._args[c_arg_name].append([])

                    self._debug(" ", self._args[c_arg_name])

                # The argument which allows params is the last one of the chain
                arg_name = "-" + arg_name_chain[len(arg_name_chain) - 1]

            self._debug(arg_name)

            if arg_name:
                # Argument taken into account, go to the next token
                i += 1
            # else: unbound argument (no - or --), allowed

            # Check if the current argument has params
            arg_params = []

            while i < len(args):
                arg_param = args[i]

                if arg_param.startswith("-"):
                    # New argument found (not a param), stop the params parsing
                    break

                # We have a param
                arg_params.append(arg_param)

                self._debug("  " + arg_param)

                i += 1

            if arg_name not in self._args:
                self._args[arg_name] = []

            # Link the params found with the current argument
            self._args[arg_name].append(arg_params)

        self._debug("_parse DONE", str(self))

    def _debug(self, *args, **kwargs):
        if Args.DEBUG:
            print(*args, **kwargs)