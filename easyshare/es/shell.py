import os
import pydoc
import shlex
import traceback
from typing import Optional, Callable, Tuple, Dict, List, Union, NoReturn

from easyshare import logging, tracing
from easyshare.args import Args, ArgsParseError, VarArgsSpec, OptIntPosArgSpec, ArgsSpec
from easyshare.consts import ansi
from easyshare.es.client import Client
from easyshare.es.errors import ClientErrors, print_errors
from easyshare.es.ui import print_tabulated, StyledString
from easyshare.helps.commands import Commands, matches_special_command, Verbose, Trace
from easyshare.helps.commands import SuggestionsIntent, COMMANDS_INFO
from easyshare.logging import get_logger
from easyshare.res.helps import get_command_help
from easyshare.tracing import get_tracing_level, set_tracing_level
from easyshare.utils.env import is_unicode_supported, is_unix, is_windows
from easyshare.utils.mathematics import rangify
from easyshare.utils.obj import values
from easyshare.utils.rl import rl_set_completer_quote_characters, rl_load, \
    rl_get_completion_quote_character, rl_set_completion_suppress_quote, \
    rl_get_completer_quote_characters
from easyshare.utils.types import is_bool

if is_unix():
    import readline as rline
else:
    rline = None


log = get_logger(__name__)

# The shell can execute every possible command, obviously
_SHELL_COMMANDS = values(Commands)


_VERBOSITY_EXPLANATION_MAP = {
    logging.VERBOSITY_NONE: Verbose.V0[1],
    logging.VERBOSITY_ERROR: Verbose.V1[1],
    logging.VERBOSITY_WARNING: Verbose.V2[1],
    logging.VERBOSITY_INFO: Verbose.V3[1],
    logging.VERBOSITY_DEBUG: Verbose.V4[1],
}

_TRACING_EXPLANATION_MAP = {
    tracing.TRACING_NONE: Trace.T0[1],
    tracing.TRACING_TEXT: Trace.T1[1],
    tracing.TRACING_BIN_PAYLOADS: Trace.T2[1],
    tracing.TRACING_BIN_ALL: Trace.T3[1],
}

class Shell:
    """
    The interactive shell of client that is able to parse and execute commands.
    Uses GNU rline for provide command completion and files suggestions.
    """
    # Quoting/Escaping GNU rline tutorial
    # https://thoughtbot.com/blog/tab-completion-in-gnu-rline
    def __init__(self, client: Client):

        self._client: Client = client

        self._prompt: str = ""
        self._current_line: str = ""

        self._suggestions_intent: Optional[SuggestionsIntent] = None

        self._shell_command_dispatcher: Dict[str, Tuple[ArgsSpec, Callable[[Args], None]]] = {
            Commands.TRACE: (OptIntPosArgSpec(), self._trace),
            Commands.VERBOSE: (OptIntPosArgSpec(), self._verbose),
            Commands.HELP: (VarArgsSpec(), self._help),
            Commands.EXIT: (VarArgsSpec(), self._exit),
            Commands.QUIT: (VarArgsSpec(), self._exit),
        }

        self._shell_command_dispatcher[Commands.TRACE_SHORT] = self._shell_command_dispatcher[Commands.TRACE]
        self._shell_command_dispatcher[Commands.VERBOSE_SHORT] = self._shell_command_dispatcher[Commands.VERBOSE]
        self._shell_command_dispatcher[Commands.HELP_SHORT] = self._shell_command_dispatcher[Commands.HELP]
        self._shell_command_dispatcher[Commands.QUIT_SHORT] = self._shell_command_dispatcher[Commands.QUIT]

        self._prompt_local_remote_sep = "\u2014" if is_unicode_supported() else "-"

        self._help_map = None

        if is_unix():
            self._init_rline()

    def input_loop(self):
        """
        Starts the shell.
        CTRL+C interrupt the current command and create a new line.
        CTRL+D exits the shell.
        """
        while True:
            try:
                log.d("Connected to server : %s%s",
                      self._client.is_connected_to_server(),
                      " ({}:{} {})".format(
                          self._client.connection.server_info.get("ip"),
                          self._client.connection.server_info.get("port"),
                          self._client.connection.server_info.get("name") or ""
                      ) if self._client.is_connected_to_server() else "")

                log.d("Connected to sharing: %s%s",
                      self._client.is_connected_to_sharing(),
                      " ({})".format(
                          self._client.connection.current_sharing_name()
                      ) if self._client.is_connected_to_sharing() else "")

                try:
                    self._prompt = self._build_prompt_string()
                except Exception as ex:
                    # Should never happen...
                    log.w(f"Prompt can't be build: {ex}")
                    self._prompt = "> " # fallback

                try:
                    print(self._prompt, flush=True, end="")
                    command_line = input()
                    # command_line = input(self._prompt)
                except EOFError:
                    log.i("\nCTRL+D: exiting")
                    self._client.destroy_connection()
                    break
                except KeyboardInterrupt:
                    log.d("\nCTRL+C")
                    print()
                    continue

                if not command_line:
                    log.w("Empty command line")
                    continue

                command_line = command_line.strip()

                try:
                    command_line_parts = shlex.split(command_line)
                except ValueError:
                    log.w("Invalid command line")
                    print_errors(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                if len(command_line_parts) < 1:
                    print_errors(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                command: str = command_line_parts[0]
                command_args: List[str] = command_line_parts[1:]

                log.d("Detected command '%s'", command)

                self.execute(command, command_args)

            except Exception:
                log.exception("Unexpected exception")
                continue


    def has_command(self, command: str) -> bool:
        """ Returns whether the shell is able to handle 'commad' """
        return command in self._shell_command_dispatcher

    def execute_shell_command(self, command: str, command_args: List[str]) -> Union[int, str, List[str]]:
        """ Executes the given 'command' using 'command_args' as arguments """
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

    def execute(self, command: str, command_args: List[str]):
        try:
            outcome = ClientErrors.COMMAND_NOT_RECOGNIZED

            if self.has_command(command):
                outcome = self.execute_shell_command(command, command_args)
            elif self._client.has_command(command):
                outcome = self._client.execute_command(command, command_args)

            print_errors(outcome)
        except ConnectionError:
            log.exception("Connection error occurred %s")
            print_errors(ClientErrors.CONNECTION_ERROR)
            self._client.destroy_connection()
        except EOFError:
            log.i("\nCTRL+D: exiting")
            self._client.destroy_connection()
            # for consistency with CTRL+D typed while reading command, exit
            exit(0)
        except KeyboardInterrupt:
            log.d("\nCTRL+C")


    def _init_rline(self):
        # GNU rline config
        rl_load()

        # TAB: autocomplete
        rline.parse_and_bind("tab: complete")

        # Show 'show all possibilities' if there are too many items
        rline.parse_and_bind("set completion-query-items 50")

        # Remove '-' from the delimiters for handle suggestions
        # starting with '-' properly and '/' for handle paths
        # `~!@#$%^&*()-=+[{]}\|;:'",<>/?
        # rline.set_completer_delims(multireplace(rline.get_completer_delims(),
        #                                      [("-", ""), ("/", "")]))

        # Use only a space as word breaker
        rline.set_completer_delims(" ")

        # Use a custom render function; this has been necessary for print
        # colors while using rline for the suggestions engine
        if is_unix():
            rline.set_completion_display_matches_hook(self._display_suggestions_wrapper)
        else:
            # FIXME
            log.w("set_completion_display_matches_hook not available; bad display")

        # Completion function
        rline.set_completer(self._next_suggestion_wrapper)

        # Set quote characters for quoting strings with spaces
        # rl_set_completer_quote_characters(b'"\'')
        rl_set_completer_quote_characters('"')

    def _display_suggestions_wrapper(self, substitution, matches, longest_match_length):
        """ Called by GNU rline when suggestions have to be rendered """
        try:
            self._display_suggestions(substitution, matches, longest_match_length)
        except:
            log.w("Exception occurred while displaying suggestions\n%s", traceback.format_exc())

    def _display_suggestions(self, substitution_help, matches, longest_match_length):
        """ Display the current suggestions """
        # Simulate the default behaviour of rline, but:
        # 1. Separate the concept of suggestion/rendered suggestion: in this
        #    way we can render a colored suggestion while using the rline
        #    core for treat it as a simple string
        # 2. Internally handles the max_columns constraints

        # eprint(f"_display_suggestions called for {len(self._suggestions_intent.suggestions)} suggs")
        print("") # break the prompt line

        # print the suggestions (without the dummy addition for avoid completion)
        real_suggestions = [s for s in self._suggestions_intent.suggestions if s.string]
        print_tabulated(real_suggestions,
                        max_columns=self._suggestions_intent.max_columns)

        # Manually print what was displayed (prompt plus content)
        print(self._prompt + self._current_line, end="", flush=True)

    def _next_suggestion_wrapper(self, token: str, count: int):
        """ Called by GNU rline when new suggestions have to be provided """
        try:
            return self._next_suggestion(token, count)
        except:
            log.w("Exception occurred while retrieving suggestions\n%s", traceback.format_exc())

    def _next_suggestion(self, token: str, count: int):
        """ Provide the next suggestion, or None if there is nothing more to suggest"""

        # Never insert trailing quote, we will do it manually
        rl_set_completion_suppress_quote(1)
        rl_get_completer_quote_characters()

        self._current_line = rline.get_line_buffer()
        stripped_current_line = self._current_line.lstrip()
        # eprint(f"\ntoken:  {token}")
        # eprint(f"\nline:  {stripped_current_line}")

        if count == 0:
            self._suggestions_intent = SuggestionsIntent([])

            for comm_name, comm_info in COMMANDS_INFO.items():
                if stripped_current_line.startswith(comm_name + " ") or \
                        matches_special_command(stripped_current_line, comm_name):
                    # Typing a COMPLETE command
                    # e.g. 'ls '
                    log.d("Fetching suggestions intent for command '%s'", comm_name)

                    self._suggestions_intent = comm_info.suggestions(
                        token, self._client
                    ) or self._suggestions_intent # don't let it to be None

                    if self._suggestions_intent:
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

            if not self._suggestions_intent.completion:
                # TODO: find a way for not show the the suggestion inline
                #  probably see https://tiswww.case.edu/php/chet/rline/rline.html#SEC45
                #  for now we add a dummy suggestion that we won't print in our
                #  custom renderer
                self._suggestions_intent.suggestions.append(StyledString(""))

            self._suggestions_intent.suggestions = \
                sorted(self._suggestions_intent.suggestions,
                       key=lambda sug: sug.string.lower())


        if count < len(self._suggestions_intent.suggestions):
            sug = self._suggestions_intent.suggestions[count].string
            log.d("Returning suggestion %d: %s", count, sug)

            # Escape whitespaces, unless this token is beginning with a quote "
            # TODO: escaping is a l
            # sug = sug.replace(" ", "\\ ")

            log.d("Completion is enabled = %s", self._suggestions_intent.completion)

            # If there is only a suggestion that begins with
            # this name, complete the suggestion (and eventually insert a space)
            if self._suggestions_intent.completion and \
                    self._suggestions_intent.space_after_completion and \
                    len(self._suggestions_intent.suggestions) == 1:

                if is_bool(self._suggestions_intent.space_after_completion):
                    append_space = self._suggestions_intent.space_after_completion
                else: # is a hook
                    append_space = self._suggestions_intent.space_after_completion(sug)

                if append_space:
                    log.d("Last command with autocomplete -> adding space required")
                    if rl_get_completion_quote_character():
                        # Insert the quote before the space
                        sug += '"'
                    sug += " "


            return sug

        return None

    # noinspection PyPep8Naming
    def _build_prompt_string(self) -> str:
        """
        Builds the prompt string of the shell based on
        the local cwd and remote connection/rcwd.
        """
        remote = ""

        if self._client.is_connected_to_server():
            remote = self._client.connection.server_info.get("name")

            if self._client.is_connected_to_sharing():
                remote += ".{}:{}".format(
                self._client.connection.current_sharing_name(),
                self._client.connection.current_rcwd()
            )

            # remote = styled(remote, fg=ansi.FG_MAGENTA, attrs=ansi.ATTR_BOLD)

        local = os.getcwd()
        # local = styled(local, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD)

        sep = (" " + 2 * self._prompt_local_remote_sep + " ") if remote else ""

        R = ansi.RESET
        B = ansi.ATTR_BOLD
        M = ansi.FG_MAGENTA
        C = ansi.FG_CYAN

        if is_windows():
            return B + M + remote + R + B + sep + R + B + C + local + R + B + "> " + R

        IS = ansi.RL_PROMPT_START_IGNORE if is_unix() else ""  # no readline on Windows for now
        IE = ansi.RL_PROMPT_END_IGNORE if is_unix() else ""  # no readline on Windows for now

        # Escape sequence must be wrapped into \001 and \002
        # so that rline can handle those well and deal with terminal/prompt
        # width properly
        # prompt = remote + sep + local + "> "

        # use a leading DELETE_EOL for overwrite eventual previously printed ^C
        # (won't overwrite the previous prompt since KeyboardInterrupt is captured
        # and prints a new line)
        prompt = ansi.DELETE_EOL + \
            ((IS + B + M + IE + remote + IS + R + IE) if remote else "") + \
            ((IS + B + IE + sep + IS + R + IE) if sep else "") + \
            IS + B + C + IE + local + IS + R + IE + \
            IS + B + IE + "> " + IS + R + IE

        return prompt

    def _help(self, args: Args) -> NoReturn:
        """ help - display the man of a command """
        cmd = args.get_positional()

        cmd_help = get_command_help(cmd)

        if not cmd_help:
            print(f"Can't provide help for command '{cmd}'")
            return

        # Pass the helps to the available pager (typically less)
        pydoc.pager(cmd_help)


    @staticmethod
    def _exit(_: Args) -> NoReturn:
        """ exit - quit the shell """
        exit(0)

    @staticmethod
    def _trace(args: Args) -> Union[int, str]:
        """ trace - changes the tracing level """

        # Increase tracing level (or disable if is already max)

        level = args.get_positional(
            default=(get_tracing_level() + 1) % (tracing.TRACING_MAX + 1)
        )

        level = rangify(level, tracing.TRACING_MIN, tracing.TRACING_MAX)

        log.i(">> TRACING (%d)", level)

        set_tracing_level(level)

        print(f"Tracing = {level} ({_TRACING_EXPLANATION_MAP.get(level, '<unknown>')})")
        return 0

    @staticmethod
    def _verbose(args: Args) -> Union[int, str]:
        """ verbose - changes the verbosity level """

        # Increase verbosity (or disable if is already max)
        root_log = get_logger()

        current_verbosity = root_log.verbosity

        verbosity = args.get_positional(
            default=(current_verbosity + 1) % (logging.VERBOSITY_MAX + 1)
        )

        verbosity = rangify(verbosity, logging.VERBOSITY_MIN, logging.VERBOSITY_MAX)

        log.i(">> VERBOSE (%d)", verbosity)

        root_log.set_verbosity(verbosity)
        # enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)

        print(f"Verbosity = {verbosity} ({_VERBOSITY_EXPLANATION_MAP.get(verbosity, '<unknown>')})")

        return 0
