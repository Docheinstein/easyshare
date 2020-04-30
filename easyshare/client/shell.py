import os
import shlex
import logging as pylogging

from typing import Optional, Callable, Tuple, Dict, List, Union, NoReturn

from Pyro4.errors import PyroError

from easyshare import logging
from easyshare.args import Args
import readline as rl

from easyshare.client.args import OptIntArg, ArgsParser, VariadicArgs
from easyshare.client.client import Client
from easyshare.client.commands import Commands, is_special_command
from easyshare.client.common import print_tabulated, StyledString
from easyshare.client.errors import print_errcode, ClientErrors
from easyshare.client.help import SuggestionsIntent, COMMANDS_INFO
from easyshare.logging import get_logger
from easyshare.tracing import is_tracing_enabled, enable_tracing
from easyshare.utils.app import eprint
from easyshare.utils.colors import styled, Attribute
from easyshare.utils.math import rangify
from easyshare.utils.obj import values
from easyshare.utils.types import is_bool, is_int, is_str

log = get_logger(__name__)


# ==================================================================


SHELL_COMMANDS = values(Commands)

VERBOSITY_EXPLANATION_MAP = {
    logging.VERBOSITY_NONE: " (disabled)",
    logging.VERBOSITY_ERROR: " (error)",
    logging.VERBOSITY_WARNING: " (error / warn)",
    logging.VERBOSITY_INFO: " (error / warn / info)",
    logging.VERBOSITY_DEBUG: " (error / warn / info / debug)",
    logging.VERBOSITY_DEBUG + 1: " (error / warn / info / debug / internal)",
}


# ==================================================================


class Shell:

    def __init__(self, client: Client):
        self._client: Client = client

        self._prompt: str = ""
        self._current_line: str = ""

        self._suggestions_intent: Optional[SuggestionsIntent] = None

        self._shell_command_dispatcher: Dict[str, Tuple[ArgsParser, Callable[[Args], None]]] = {
            Commands.TRACE: (OptIntArg(), self._trace),
            Commands.TRACE_SHORT: (OptIntArg(), self._trace),
            Commands.VERBOSE: (OptIntArg(), self._verbose),
            Commands.VERBOSE_SHORT: (OptIntArg(), self._verbose),

            Commands.HELP: (VariadicArgs(), self._help),
            Commands.EXIT: (VariadicArgs(), self._exit),
        }

        rl.parse_and_bind("tab: complete")
        rl.parse_and_bind("set completion-query-items 50")

        # Remove '-' from the delimiters for handle suggestions
        # starting with '-' properly
        # `~!@#$%^&*()-=+[{]}\|;:'",<>/?
        rl.set_completer_delims(rl.get_completer_delims().replace("-", ""))

        rl.set_completion_display_matches_hook(self._display_suggestions)

        rl.set_completer(self._next_suggestion)

    def input_loop(self):
        while True:
            try:
                self._prompt = self._build_prompt_string()
                # print(self._prompt, end="", flush=True)
                command_line = input(self._prompt)

                if not command_line:
                    log.w("Empty command line")
                    continue

                try:
                    command_line_parts = shlex.split(command_line)
                except ValueError:
                    log.w("Invalid command line")
                    print_errcode(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                if len(command_line_parts) < 1:
                    print_errcode(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                command: str = command_line_parts[0]
                command_args: List[str] = command_line_parts[1:]

                log.d("Detected command '%s'", command)

                outcome = ClientErrors.COMMAND_NOT_RECOGNIZED

                if self.has_command(command):
                    outcome = self.execute_shell_command(command, command_args)
                elif self._client.has_command(command):
                    outcome = self._client.execute_command(command, command_args)

                if is_int(outcome) and outcome > 0:
                    print_errcode(outcome)
                elif is_str(outcome):
                    eprint(outcome)
                else:
                    log.d("Command execution: OK")

            except PyroError as pyroerr:
                log.e("Pyro error occurred %s", pyroerr)
                print_errcode(ClientErrors.CONNECTION_ERROR)
                # Close client connection anyway
                try:
                    if self._client.is_connected():
                        log.d("Trying to close connection gracefully")
                        self._client.close(None)
                except PyroError:
                    log.d("Cannot communicate with remote: invalidating connection")
                    self._client.connection = None
            except KeyboardInterrupt:
                log.d("\nCTRL+C")
                print()
            except EOFError:
                log.i("\nCTRL+D: exiting")
                if self._client.is_connected():
                    self._client.close(None)
                break

    def has_command(self, command: str) -> bool:
        return command in self._shell_command_dispatcher

    def execute_shell_command(self, command: str, command_args: List[str]) -> Union[int, str]:
        if not self.has_command(command):
            return ClientErrors.COMMAND_NOT_RECOGNIZED

        log.i("Handling shell command %s (%s)", command, command_args)

        parser, executor = self._shell_command_dispatcher[command]

        # Parse args using the parsed bound to the command
        args = parser.parse(command_args)

        if not args:
            log.e("Command's arguments parse failed")
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.i("Parsed command arguments\n%s", args)

        try:
            executor(args)
        except Exception as ex:
            log.exception("Exception caught while executing command\n%s", ex)
            return ClientErrors.COMMAND_EXECUTION_FAILED

        return 0

    def _display_suggestions(self, substitution, matches, longest_match_length):
        # Simulate the default behaviour of readline, but:
        # 1. Separate the concept of suggestion/rendered suggestion: in this
        #    way we can render a colored suggestion while using the readline
        #    core for treat it as a simple string
        # 2. Internally handles the max_columns constraints
        print("")
        print_tabulated(self._suggestions_intent.suggestions,
                        max_columns=self._suggestions_intent.max_columns)
        print(self._prompt + self._current_line, end="", flush=True)

    def _next_suggestion(self, token: str, count: int):
        self._current_line = rl.get_line_buffer()

        stripped_current_line = self._current_line.lstrip()

        if count == 0:
            self._suggestions_intent = SuggestionsIntent([])

            for comm_name, comm_info in COMMANDS_INFO.items():
                if stripped_current_line.startswith(comm_name + " ") or \
                        is_special_command(comm_name):
                    # Typing a COMPLETE command
                    # e.g. 'ls '
                    log.d("Fetching suggestions intent for command '%s'", comm_name)

                    self._suggestions_intent = comm_info.suggestions(
                        token, stripped_current_line, self._client)

                    log.d("Fetched (%d) suggestions intent for command '%s'",
                          len(self._suggestions_intent.suggestions),
                          comm_name
                      )

                    break

                if comm_name.startswith(stripped_current_line):
                    # Typing an INCOMPLETE command
                    # e.g. 'clos '

                    # Case 1: complete command
                    self._suggestions_intent.suggestions.append(StyledString(comm_name))

            # If there is only a command that begins with
            # this name, complete the command (and eventually insert a space)
            if self._suggestions_intent.completion and \
                    self._suggestions_intent.space_after_completion and \
                    len(self._suggestions_intent.suggestions) == 1:

                if is_bool(self._suggestions_intent.space_after_completion):
                    append_space = self._suggestions_intent.space_after_completion
                else:
                    # Hook
                    append_space = self._suggestions_intent.space_after_completion(
                        self._suggestions_intent.suggestions[0].string
                    )

                if append_space:
                    self._suggestions_intent.suggestions[0].string += " "

            self._suggestions_intent.suggestions = \
                sorted(self._suggestions_intent.suggestions,
                       key=lambda sug: sug.string.lower())

        if count < len(self._suggestions_intent.suggestions):
            log.d("Returning suggestion %d", count)
            sug = self._suggestions_intent.suggestions[count].string

            # Escape whitespaces
            return sug.replace(" ", "\\ ")

        return None

    def _build_prompt_string(self):
        remote = ""

        if self._client.is_connected():
            remote = "{}:/{}".format(
                self._client.connection.sharing_name(),
                self._client.connection.rpwd()
            )
            # remote = fg(remote, color=Color.MAGENTA)

        local = os.getcwd()
        # local = fg(local, color=Color.CYAN)

        sep = "  ##  " if remote else ""

        prompt = remote + sep + local + "> "

        return styled(prompt, attrs=Attribute.BOLD)

    @classmethod
    def _help(cls, _: Args) -> Union[int, str]:
        print("HELP")
        return 0

    @classmethod
    def _exit(cls, _: Args) -> NoReturn:
        exit(0)

    @classmethod
    def _trace(cls, args: Args) -> Union[int, str]:
        # Toggle tracing if no parameter is provided
        enable = args.get_varg(default=not is_tracing_enabled())

        log.i(">> TRACE (%d)", enable)

        enable_tracing(enable)

        print("Tracing = {:d}{}".format(
            enable,
            " (enabled)" if enable else " (disabled)"
        ))

        return 0

    @classmethod
    def _verbose(cls, args: Args) -> Union[int, str]:
        # Increase verbosity (or disable if is already max)
        root_log = get_logger()

        verbosity = args.get_varg(
            default=(root_log.verbosity + 1) % (logging.VERBOSITY_MAX + 2)
        )

        verbosity = rangify(verbosity, logging.VERBOSITY_MIN, logging.VERBOSITY_MAX + 1)

        log.i(">> VERBOSE (%d)", verbosity)

        root_log.set_verbosity(verbosity)

        if verbosity > logging.VERBOSITY_MAX:
            log.d("Enabling pyro logging to DEBUG")
            pyro_log = pylogging.getLogger("Pyro4")
            pyro_log.setLevel(pylogging.DEBUG)

        print("Verbosity = {:d}{}".format(
            verbosity,
            VERBOSITY_EXPLANATION_MAP.get(verbosity, "")
        ))

        return 0
