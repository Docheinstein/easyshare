import os
import shlex
import readline as rl
import traceback

from typing import Optional, Callable, Tuple, Dict, List, Union, NoReturn

from Pyro5.errors import PyroError

from easyshare import logging, helps
from easyshare.args import Args, ArgsParseError, VariadicArgs, OptIntArg, ArgsParser
from easyshare.consts import ansi

from easyshare.es.client import Client
from easyshare.es.commands import Commands, matches_special_command, Verbose
from easyshare.es.ui import print_tabulated, StyledString
from easyshare.es.errors import print_error, ClientErrors
from easyshare.es.commands import SuggestionsIntent, COMMANDS_INFO
from easyshare.logging import get_logger
from easyshare.styling import styled, fg, bold
from easyshare.tracing import is_tracing_enabled, enable_tracing
from easyshare.utils.app import eprint
from easyshare.utils.env import is_unicode_supported
from easyshare.utils.hmd import help_markdown_pager
from easyshare.utils.math import rangify
from easyshare.utils.obj import values
from easyshare.utils.pyro.common import enable_pyro_logging, is_pyro_logging_enabled
from easyshare.utils.types import is_bool, is_int, is_str, bool_to_str

log = get_logger(__name__)


# ==================================================================


SHELL_COMMANDS = values(Commands)

VERBOSITY_EXPLANATION_MAP = {
    logging.VERBOSITY_NONE: Verbose.V0[1],
    logging.VERBOSITY_ERROR: Verbose.V1[1],
    logging.VERBOSITY_WARNING: Verbose.V2[1],
    logging.VERBOSITY_INFO: Verbose.V3[1],
    logging.VERBOSITY_DEBUG: Verbose.V4[1],
    logging.VERBOSITY_DEBUG + 1: Verbose.V5[1]
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
            Commands.VERBOSE: (OptIntArg(), self._verbose),
            Commands.HELP: (VariadicArgs(), self._help),
            Commands.EXIT: (VariadicArgs(), self._exit),
            Commands.QUIT: (VariadicArgs(), self._exit),
        }

        self._shell_command_dispatcher[Commands.TRACE_SHORT] = self._shell_command_dispatcher[Commands.TRACE]
        self._shell_command_dispatcher[Commands.VERBOSE_SHORT] = self._shell_command_dispatcher[Commands.VERBOSE]
        self._shell_command_dispatcher[Commands.HELP_SHORT] = self._shell_command_dispatcher[Commands.HELP]
        self._shell_command_dispatcher[Commands.QUIT_SHORT] = self._shell_command_dispatcher[Commands.QUIT]

        self._prompt_local_remote_sep = "\u2014" if is_unicode_supported() else "-"

        rl.parse_and_bind("tab: complete")
        rl.parse_and_bind("set completion-query-items 50")

        # Remove '-' from the delimiters for handle suggestions
        # starting with '-' properly
        # `~!@#$%^&*()-=+[{]}\|;:'",<>/?
        rl.set_completer_delims(rl.get_completer_delims().replace("-", ""))

        rl.set_completion_display_matches_hook(self._display_suggestions_wrapper)

        rl.set_completer(self._next_suggestion_wrapper)

    def input_loop(self):
        while True:
            try:
                log.d("========================\n"
                      "Connected to esd : %s%s\n"
                      "Connected to sharing: %s%s",
                      self._client.is_connected_to_server(),
                      " ({}:{} {})".format(
                          self._client.server_connection.server_info.get("ip"),
                          self._client.server_connection.server_info.get("port"),
                          self._client.server_connection.server_info.get("name") or ""
                      ) if self._client.is_connected_to_server() else "",
                      self._client.is_connected_to_sharing(),
                      " ({})".format(
                          self._client.sharing_connection.sharing_info.get("name")
                      ) if self._client.is_connected_to_sharing() else "",
                )

                self._prompt = self._build_prompt_string()
                # print(self._prompt, end="", flush=True)
                command_line = input(self._prompt)

                if not command_line:
                    log.w("Empty command line")
                    continue

                command_line = command_line.strip()

                try:
                    command_line_parts = shlex.split(command_line)
                except ValueError:
                    log.w("Invalid command line")
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                if len(command_line_parts) < 1:
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
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
                    print_error(outcome)
                elif is_str(outcome):
                    eprint(outcome)
                else:
                    log.d("Command execution: OK")

            except PyroError as pyroerr:
                log.exception("Pyro error occurred %s", pyroerr)
                print_error(ClientErrors.CONNECTION_ERROR)
                self._client.destroy_connection()
                break

            except EOFError:
                log.i("\nCTRL+D: exiting")
                self._client.destroy_connection()
                break

            except KeyboardInterrupt:
                log.d("\nCTRL+C")
                print()


    def has_command(self, command: str) -> bool:
        return command in self._shell_command_dispatcher

    def execute_shell_command(self, command: str, command_args: List[str]) -> Union[int, str]:
        if not self.has_command(command):
            return ClientErrors.COMMAND_NOT_RECOGNIZED

        log.i("Handling shell command %s (%s)", command, command_args)

        parser, executor = self._shell_command_dispatcher[command]

        # Parse args using the parsed bound to the command
        try:
            args = parser.parse(command_args)
        except ArgsParseError as err:
            log.e("Command's arguments parse failed: %s", str(err))
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.i("Parsed command arguments\n%s", args)

        try:
            executor(args)
        except Exception as ex:
            log.exception("Exception caught while executing command\n%s", ex)
            return ClientErrors.COMMAND_EXECUTION_FAILED

        return 0


    def _display_suggestions_wrapper(self, substitution, matches, longest_match_length):
        try:
            self._display_suggestions(substitution, matches, longest_match_length)
        except:
            log.w("Exception occurred while displaying suggestions\n%s", traceback.format_exc())

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

    def _next_suggestion_wrapper(self, token: str, count: int):
        try:
            return self._next_suggestion(token, count)
        except:
            log.w("Exception occurred while retrieving suggestions\n%s", traceback.format_exc())

    def _next_suggestion(self, token: str, count: int):
        self._current_line = rl.get_line_buffer()

        stripped_current_line = self._current_line.lstrip()

        if count == 0:
            self._suggestions_intent = SuggestionsIntent([])

            for comm_name, comm_info in COMMANDS_INFO.items():
                if stripped_current_line.startswith(comm_name + " ") or \
                        matches_special_command(stripped_current_line, comm_name):
                    # Typing a COMPLETE command
                    # e.g. 'ls '
                    log.d("Fetching suggestions intent for command '%s'", comm_name)

                    self._suggestions_intent = comm_info.suggestions(
                        token, stripped_current_line, self._client)

                    log.d("Fetched (%d) suggestions intent for command '%s'",
                          len(self._suggestions_intent.suggestions),
                          comm_name)
                    break

                if comm_name.startswith(stripped_current_line):
                    # Typing an INCOMPLETE command
                    # e.g. 'clos '

                    # Case 1: complete command
                    log.d("Fetching suggestions for command completion of '%s'", comm_name)
                    self._suggestions_intent.suggestions.append(StyledString(comm_name))

            self._suggestions_intent.suggestions = \
                sorted(self._suggestions_intent.suggestions,
                       key=lambda sug: sug.string.lower())

        if count < len(self._suggestions_intent.suggestions):
            log.d("Returning suggestion %d", count)
            sug = self._suggestions_intent.suggestions[count].string

            # Escape whitespaces
            sug = sug.replace(" ", "\\ ")

            # If there is only a command that begins with
            # this name, complete the command (and eventually insert a space)
            if self._suggestions_intent.completion and \
                    self._suggestions_intent.space_after_completion and \
                    count == len(self._suggestions_intent.suggestions) - 1:

                if is_bool(self._suggestions_intent.space_after_completion):
                    append_space = self._suggestions_intent.space_after_completion
                else:
                    # Hook
                    append_space = self._suggestions_intent.space_after_completion(
                        sug
                    )

                if append_space:
                    sug += " "

            return sug

        return None

    def _build_prompt_string(self):
        remote = ""

        if self._client.is_connected_to_server():
            remote = self._client.server_connection.server_info.get("name")

            if self._client.is_connected_to_sharing():
                remote += ".{}:/{}".format(
                self._client.sharing_connection.sharing_info.get("name"),
                self._client.sharing_connection.rcwd()
            )

            # remote = styled(remote, fg=ansi.FG_MAGENTA, attrs=ansi.ATTR_BOLD)

        local = os.getcwd()
        # local = styled(local, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD)

        sep = (" " + 1 * self._prompt_local_remote_sep + " ") if remote else ""

        prompt = bold(remote + sep + local + "> ")
        # prompt = bold(remote + sep + local + "> ")
        # prompt = \
        #     ansi.ATTR_BOLD + ansi.FG_CYAN + local + ansi.RESET + \
        #     ansi.ATTR_BOLD + sep +  ansi.FG_MAGENTA + remote + ansi.RESET + \
        #     ansi.ATTR_BOLD + "> " + ansi.RESET

        # prompt = \
        #     ansi.FG_MAGENTA + remote + ansi.RESET + \
        #     sep +  ansi.FG_CYAN + local + ansi.RESET + \
        #     "> " + ansi.RESET

        # assert prompt == prompt2, "mismatch {} != {}".format(prompt, prompt2)
        # return styled(prompt, attrs=ansi.ATTR_BOLD)
        return prompt

    @staticmethod
    def _help(args: Args) -> NoReturn:
        cmd = args.get_varg()
        if not cmd:
            cmd_help = helps.USAGE
        else:
            # Show the help of cmd if found on helps.py
            cmd_help = getattr(helps, cmd.upper(), None)

        if not cmd_help:
            eprint("Help not found for command {}".format(cmd))
            return

        print(help_markdown_pager(cmd_help), end="")

    @staticmethod
    def _exit(cls, _: Args) -> NoReturn:
        exit(0)

    @staticmethod
    def _trace(args: Args) -> Union[int, str]:
        # Toggle tracing if no parameter is provided
        enable = args.get_varg(default=not is_tracing_enabled())

        log.i(">> TRACE (%d)", enable)

        enable_tracing(enable)

        print("Tracing = {:d} ({})".format(
            enable,
            bool_to_str(enable, "enabled", "disabled")
        ))

        return 0

    @staticmethod
    def _verbose(args: Args) -> Union[int, str]:
        # Increase verbosity (or disable if is already max)
        root_log = get_logger(logging.ROOT_LOGGER_NAME)

        current_verbosity = root_log.verbosity + is_pyro_logging_enabled()

        verbosity = args.get_varg(
            default=(current_verbosity + 1) % (logging.VERBOSITY_MAX + 2)
        )

        verbosity = rangify(verbosity, logging.VERBOSITY_MIN, logging.VERBOSITY_MAX + 1)

        log.i(">> VERBOSE (%d)", verbosity)

        root_log.set_verbosity(verbosity)
        enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)

        print("Verbosity = {:d} ({})".format(
            verbosity,
            VERBOSITY_EXPLANATION_MAP.get(verbosity, "<unknown>")
        ))

        return 0
