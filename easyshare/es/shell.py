import os
import re
import traceback
from pathlib import Path
from typing import Optional, Callable, Tuple, Dict, List, Union, NoReturn, Type
from easyshare import logging, tracing
from easyshare.args import Args, ArgsParseError, VarArgsSpec, OptIntPosArgSpec, ArgsSpec
from easyshare.common import EASYSHARE_HISTORY
from easyshare.consts import ansi
from easyshare.es.client import Client, HandledKeyboardInterrupt
from easyshare.es.errors import ClientErrors, print_errors
from easyshare.es.ui import print_tabulated, StyledString
from easyshare.commands.commands import Commands, Verbose, Trace, COMMANDS, CommandInfo, Ls
from easyshare.commands.commands import SuggestionsIntent, COMMANDS_INFO
from easyshare.logging import get_logger
from easyshare.res.helps import command_man
from easyshare.styling import is_styling_enabled, red

from easyshare.tracing import get_tracing_level, set_tracing_level
from easyshare.utils.env import is_unicode_supported, has_gnureadline, has_pyreadline
from easyshare.utils.mathematics import rangify
from easyshare.utils.obj import values
from easyshare.utils.rl import rl_set_completer_quote_characters, rl_load, \
    rl_get_completion_quote_character, rl_set_completion_suppress_quote, rl_set_char_is_quoted_p
from easyshare.utils.str import isorted
from easyshare.utils.types import is_bool, is_str

import readline

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
    tracing.TRACING_BIN: Trace.T2[1],
}

class Shell:
    """
    The interactive shell of client that is able to parse and execute commands.
    Uses GNU rline for provide command completion and files suggestions.
    """

    LOCAL_FINDINGS_RE = re.compile(r"^\$([a-z]\d+)$")
    REMOTE_FINDINGS_RE = re.compile(r"^\$([A-Z]\d+)$")

    ALIAS_RESOLUTION_MAX_DEPTH = 100

    # Quoting/Escaping GNU rline tutorial
    # https://thoughtbot.com/blog/tab-completion-in-gnu-rline
    def __init__(self, client: Client, passthrough: bool=False):
        log.i(f"Shell passthrough = {passthrough}")

        self._aliases: Dict[str, str] = {}
        self._available_commands: Dict[str, Type[CommandInfo]] = dict(COMMANDS_INFO)

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

        self._prompt_local_remote_sep = "\u2014" if is_unicode_supported() else "-"

        self._passthrough = passthrough

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
                    self._prompt = "> "  # fallback

                try:
                    # print(self._prompt, flush=True, end="")
                    command_line = input(self._prompt)
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
                log.d(f"Detected command {command_line}")
                self.execute(command_line)

            except Exception:
                log.exception("Unexpected exception")
                continue


    def has_command(self, command: str) -> bool:
        """ Returns whether the shell is able to handle 'commad' """
        return command in self._shell_command_dispatcher

    def execute(self, cmd: str):
        outcome = self._execute(cmd)
        print_errors(outcome)

    def _execute(self, cmd: str) ->  Union[int, str, List[str]]:
        self._update_history()

        if not is_str(cmd):
            log.e("Invalid command")
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.d(f"Before alias resolution: {cmd}")
        resolved_cmd_prefix, resolved_cmd_suffix = self._resolve_alias(cmd, as_string=False)
        log.d(f"resolved_cmd_prefix: {resolved_cmd_prefix}")
        log.d(f"resolved_cmd_suffix: {resolved_cmd_suffix}")
        # 'command_prefix' might be partial (unique prefix of a valid command)
        commands = self._commands_for(resolved_cmd_prefix, resolve_alias=False)
        log.d(f"Commands found: {commands}")

        # No command
        if len(commands) == 0:
            if self._passthrough:
                log.d("Passing unknown command to underlying shell due to passthrough")
                return self._client.execute_command(Commands.LOCAL_SHELL, cmd)

            return ClientErrors.COMMAND_NOT_RECOGNIZED

        # More than a command for this prefix
        if len(commands) > 1 and resolved_cmd_prefix not in commands:
            print("Available commands: ")
            for comm in isorted(commands):
                print(red(resolved_cmd_prefix) + comm[len(resolved_cmd_prefix):])
            return ClientErrors.SUCCESS

        if len(commands) == 1:
            # Just 1 command found
            command = commands[0]
        else:
            # More than a command, but one matches exactly
            command = resolved_cmd_prefix

        # Exactly a known command, execute it
        try:
            outcome = ClientErrors.COMMAND_NOT_RECOGNIZED

            if self.has_command(command):
                outcome = self._execute_shell_command(command, resolved_cmd_suffix)
            elif self._client.has_command(command):
                outcome = self._client.execute_command(command, resolved_cmd_suffix)

            log.d(f"Command outcome: {outcome}")

            return outcome
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

    def _execute_shell_command(self, command: str, command_suffix: str) -> Union[int, str, List[str]]:
        """ Executes the given 'command' using 'command_args' as arguments """
        if not self.has_command(command):
            return ClientErrors.COMMAND_NOT_RECOGNIZED

        log.i(f"Handling shell command {command} {command_suffix}")

        parser, executor = self._shell_command_dispatcher[command]

        # Parse args using the parsed bound to the command
        try:
            args = parser.parse(command_suffix)
        except ArgsParseError as err:
            log.e("Command's arguments parse failed: %s", str(err))
            return ClientErrors.INVALID_COMMAND_SYNTAX

        log.i("Parsed command arguments\n%s", args)

        try:
            executor(args)
            return ClientErrors.SUCCESS
        except Exception as ex:
            log.exception("Exception caught while executing command\n%s", ex)
            return ClientErrors.COMMAND_EXECUTION_FAILED

    # noinspection PyUnresolvedReferences
    def _init_rline(self):
        log.d("Init GNU readline")

        # [GNU] readline config
        rl_load()

        # TAB: autocomplete
        readline.parse_and_bind("tab: complete")
        # readline.parse_and_bind("set show-all-if-ambiguous on")
        # readline.parse_and_bind("set show-all-if-unmodified on")
        # readline.parse_and_bind("set menu-complete-display-prefix on")
        # readline.parse_and_bind("tab: complete")

        # Show 'show all possibilities' if there are too many items
        readline.parse_and_bind("set completion-query-items 50")
        readline.parse_and_bind("set completion-ignore-case on")
        readline.parse_and_bind("set echo-control-characters off")

        # Remove '-' from the delimiters for handle suggestions
        # starting with '-' properly and '/' for handle paths
        # `~!@#$%^&*()-=+[{]}\|;:'",<>/?
        # readline.set_completer_delims(multireplace(readline.get_completer_delims(),
        #                                      [("-", ""), ("/", "")]))

        # Completion function
        readline.set_completer(self._next_suggestion)

        # Use only a space as word breaker
        readline.set_completer_delims(" ")

        # Use a custom render function; this has been necessary for print
        # colors while using rline for the suggestions engine
        if has_gnureadline():
            readline.set_completion_display_matches_hook(self._display_suggestions_gnureadline)
        elif has_pyreadline():
            readline.rl.mode._display_completions = self._display_suggestions_pyreadline

        # Set quote characters for quoting strings with spaces
        rl_set_completer_quote_characters('"')

        rl_set_char_is_quoted_p(self._quote_detector)

        # History

        self._load_history()


    @staticmethod
    def _load_history():
        es_history = Path.home() / EASYSHARE_HISTORY
        if not es_history.exists():
            try:
                es_history.touch()
            except:
                log.w(f"Failed to create {es_history}")

        if es_history.exists():
            try:
                log.d(f"Loading history from: '{es_history}'")
                readline.read_history_file(es_history)
                log.d(f"readline.get_current_history_length() = {readline.get_current_history_length()}")
                log.d(f"readline.get_history_length() = {readline.get_history_length()}")
            except OSError as e:
                log.w(f"Failed to load history file: {e}")
        else:
            log.w(f"History file not found at: '{es_history}'")

    @staticmethod
    def _update_history():
        es_history = Path.home() / EASYSHARE_HISTORY

        log.d(f"Saving readline history file at: '{es_history}'")
        readline.append_history_file(1, es_history)
        log.d(f"readline.get_current_history_length() = {readline.get_current_history_length()}")
        log.d(f"readline.get_history_length() = {readline.get_history_length()}")

    # For Windows
    # noinspection PyUnresolvedReferences
    def _display_suggestions_pyreadline(self, matches):
        """
        Called by GNU pyreadline when suggestions have to be rendered.
        Display the current suggestions.
        """
        try:
            readline.rl.mode.console.write("\n")

            # print the suggestions (without the dummy addition for avoid completion)
            real_suggestions = [s for s in self._suggestions_intent.suggestions if s.string]
            print_tabulated(real_suggestions,
                            max_columns=self._suggestions_intent.max_columns,
                            print_func=readline.rl.mode.console.write)

            # Manually print what was displayed (prompt plus content)
            # noinspection PyProtectedMember
            readline.rl.mode._print_prompt()

        except:
            log.w("Exception occurred while displaying suggestions\n%s", traceback.format_exc())

    # For Unix
    def _display_suggestions_gnureadline(self, substitution_help, matches, longest_match_length):
        """
        Called by GNU readline when suggestions have to be rendered.
        Display the current suggestions.
        """
        try:

            # Simulate the default behaviour of readline, but:
            # 1. Separate the concept of suggestion/rendered suggestion: in this
            #    way we can render a colored suggestion while using the readline
            #    core for treat it as a simple string
            # 2. Internally handles the max_columns constraints

            # eprint(f"_display_suggestions called for {len(self._suggestions_intent.suggestions)} suggs")
            print("")  # break the prompt line

            # print the suggestions (without the dummy addition for avoid completion)
            real_suggestions = [s for s in self._suggestions_intent.suggestions if s.string]
            print_tabulated(real_suggestions,
                            max_columns=self._suggestions_intent.max_columns)

            # Manually print what was displayed (prompt plus content)
            print(self._prompt + self._current_line, end="", flush=True)
        except:
            log.w("Exception occurred while displaying suggestions\n%s", traceback.format_exc())


    COMM_SPACE_RE = re.compile(".* $")

    def _next_suggestion(self, token: str, count: int):
        """
        Called by GNU readline when new suggestions have to be provided.
        Provide the next suggestion, or None if there is nothing more to suggest.
        """

        def escape(s: str):
            return s.replace(" ", "\\ ")

        def unescape(s: str):
            return s.replace("\\ ", " ")


        try:
            log.d(f"next_suggestion, token='{token}' | count={count}")

            # Never insert trailing quote, we will do it manually
            # (this is needed because for directory completion we should not
            # insert the trailing quote)
            rl_set_completion_suppress_quote(1)
            is_quoting = rl_get_completion_quote_character() == ord('"')

            if count == 0:

                self._current_line = readline.get_line_buffer()
                line = self._current_line.lstrip()

                # Unescape since the token might contain \ we inserted in next_suggestion
                # for allow spaces in the line
                token = unescape(token)
                line = unescape(line)

                # Detect the command (first token of the line) by resolving aliases
                # and figure out if the command is unique for the given prefix
                log.d(f"Cmd line: '{line}'")
                resolved_line = self._resolve_alias(line, as_string=True)
                resolved_command = self._command_for(resolved_line, resolve_alias=False)
                log.d(f"resolved_line: '{resolved_line}'")
                log.d(f"resolved_command: '{resolved_command}'")


                self._suggestions_intent = SuggestionsIntent([])

                for comm_name, comm_info in self._available_commands.items():
                    comm_resolved_name = comm_info.name() # comm_name might be an alias

                    log.d(f" Checking comm_name='{comm_name}'")
                    if resolved_command == comm_name and \
                            re.match(Shell.COMM_SPACE_RE, resolved_line):
                        # Typing a COMPLETE command
                        # e.g. 'ls \t'
                        log.d("Fetching suggestions for COMMAND INTENT '%s'", comm_resolved_name)

                        comms_sugg  = comm_info.suggestions(token, self._client)
                        if comms_sugg:
                            # don't let it to be None
                            self._suggestions_intent = comms_sugg

                            log.d("Fetched (%d) suggestions INTENT for command '%s'",
                                  len(self._suggestions_intent.suggestions),
                                  comm_name)

                        break # nothing more to complete, the command has been found

                    if comm_name.startswith(line):
                        # Typing an INCOMPLETE command
                        # e.g. 'clos\t'

                        # Case 1: complete command
                        log.d("Adding suggestion for COMMAND COMPLETION of '%s'", comm_resolved_name)
                        self._suggestions_intent.suggestions.append(StyledString(comm_name))

                # If there are no suggestions and we are doing shell passthrough
                # show the local files (probably the user command acts on those)
                if len(self._suggestions_intent.suggestions) == 0 and self._passthrough:
                    log.d("Showing local files as suggestions as fallback, "
                          "since shell passthrough is enabled")
                    self._suggestions_intent = Ls.suggestions(token, self._client) \
                                               or self._suggestions_intent

                findings = None
                if re.match(Shell.LOCAL_FINDINGS_RE, token):
                    findings = self._client.get_local_findings(token)
                elif re.match(Shell.REMOTE_FINDINGS_RE, token):
                    findings = self._client.get_remote_findings(token)

                if findings and len(findings) == 1:
                    finding_info = findings[0]
                    log.d(f"Found single finding for token: {finding_info}")
                    return str(Path(findings.path) / finding_info.get("name"))

                if not self._suggestions_intent.completion:
                    # TODO: find a way for not show the the suggestion inline
                    #  probably see https://tiswww.case.edu/php/chet/readline/readline.html#SEC45
                    #  for now we add a dummy suggestion that we won't print in our
                    #  custom renderer
                    self._suggestions_intent.suggestions.append(StyledString(""))

                self._suggestions_intent.suggestions = sorted(
                    self._suggestions_intent.suggestions, key=lambda s: s.string.lower()
                )

            if count < len(self._suggestions_intent.suggestions):
                sug = self._suggestions_intent.suggestions[count].string

                # Eventually escape it
                if not is_quoting:
                    sug = escape(sug)

                log.d("Returning suggestion %d: %s", count, sug)
                log.d("Completion is enabled = %s", self._suggestions_intent.completion)

                # If there is only a suggestion that begins with
                # this name, complete the suggestion (and eventually insert a space)
                if self._suggestions_intent.completion and \
                        self._suggestions_intent.space_after_completion and \
                        len(self._suggestions_intent.suggestions) == 1:


                    if is_bool(self._suggestions_intent.space_after_completion):
                        append_space = self._suggestions_intent.space_after_completion
                    else:  # is a hook
                        append_space = self._suggestions_intent.space_after_completion(sug)

                    if append_space:
                        log.d("Last command with autocomplete -> adding space required")
                        if is_quoting:
                            # Insert the quote before the space
                            sug += '"'
                        sug += " "

                return sug

            log.d("END OF suggestions")
            return None
        except:
            log.w("Exception occurred while retrieving suggestions\n%s", traceback.format_exc())
            return None

    @staticmethod
    def _quote_detector(text: str, index: int) -> int:
        """
        l_char_is_quoted_p callback called from GNU readline
        """
        is_quoted = 1 if (index > 0 and text[index] == " " and text[index - 1] == "\\") else 0
        log.d(f"\n_quote_detector('{text}', {index}) -> '{text[index]}', is quoted = {is_quoted}")
        return is_quoted

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

        local = os.getcwd()

        sep = (" " + 2 * self._prompt_local_remote_sep + " ") if remote else ""

        styled = is_styling_enabled()
        R = ansi.RESET if styled else ""
        B = ansi.ATTR_BOLD if styled else ""
        M = ansi.FG_MAGENTA if styled else ""
        C = ansi.FG_CYAN if styled else ""
        IS = ansi.RL_PROMPT_START_IGNORE if styled else ""
        IE = ansi.RL_PROMPT_END_IGNORE if styled else ""

        # Escape sequence must be wrapped into \001 and \002
        # so that readline can handle those well and deal with terminal/prompt
        # width properly
        # use a leading DELETE_EOL for overwrite eventual previously printed ^C
        # (won't overwrite the previous prompt since KeyboardInterrupt is captured
        # and prints a new line)
        # prompt = IS + ansi.RESET_LINE + IE + \

        prompt = \
                 ((IS + B + M + IE + remote + IS + R + IE) if remote else "") + \
                 ((IS + B + IE + sep + IS + R + IE) if sep else "") + \
                 IS + B + C + IE + local + IS + R + IE + \
                 IS + B + IE + "> " + IS + R + IE

        return prompt



    def add_alias(self, source: str, target: str):
        log.i(f"Adding alias: '{source}'='{target}'")
        self._aliases[source] = target
        comm_info = COMMANDS_INFO.get(self._command_for(source))
        if comm_info:
            self._available_commands[source] = comm_info

        #
        # # Try to retrieve the target CommandInfo of the alias for
        # # treat it as a stock command
        # cur_alias_target_comm = source
        # target_comm = None
        # for i in range(Shell.ALIAS_RESOLUTION_MAX_DEPTH):
        #     # Is this (the first token) already a valid command?
        #     leading = lexer.split(cur_alias_target_comm)[0]
        #     target_comm_str = self._command_for_prefix(leading)
        #     if target_comm_str:
        #         target_comm = COMMANDS_INFO.get(target_comm_str)
        #         break
        #
        #     # Resolve it, for next iter
        #     cur_alias_target_comm = self._resolve_alias(leading)
        #     log.d(f"cur_alias_target_comm: {cur_alias_target_comm}")
        #
        #     if not cur_alias_target_comm:
        #         # No more substitution to do, alias does not
        #         # refer to a valid command
        #         log.w(f"Invalid alias detected: {source} (does not lead to a command)")
        #         break
        # else:
        #     print_errors(f"Infinite alias substitution detected: {source} - "
        #                  f"fix {EASYSHARE_ES_CONF} file")
        #
        # if target_comm:
        #     log.d(f"Valid alias to command resolution {source} -> {target_comm.name()}")
        #     self._available_commands[source] = target_comm

    # def _commands_for_prefix(self, prefix: str) -> List[CommandInfo]:
    #     return [comm for (comm_name, comm) in self._available_commands if comm_name.startswith(prefix)]
    #
    # def _command_for_prefix(self, prefix: str, default=None) -> Optional[CommandInfo]:
    #     comms = self._commands_for_prefix(prefix)
    #     return comms[0] if comms else default
    #


    def _command_for(self, string: str, resolve_alias: bool=True) -> Optional[str]:
        cmds = self._commands_for(string, resolve_alias=resolve_alias)
        if not cmds:
            return None
        return cmds[0]

    def _commands_for(self, string: str, resolve_alias: bool=True) -> List[str]:
        """
        Resolves a string and turns it into a command or a list of commands,
        based on the longest prefix match, performing alias resolution in the meanwhile.
        e.g.
            rsh -> [rshell]
            p -> [put]
            s -> [shell, scan]

        ----
        e.g.
            alias :=exe
            alias ::=rex
            alias cat=: cat

            e -> [exec, exit]
            : -> [exec, rexec]
            cat -> [exec]
        """

        if not string:
            return []

        if resolve_alias:
            command, _ = self._resolve_alias(string, as_string=False)
        else:
            command = string.split(" ")[0]

        cmds = [c for c in COMMANDS if c.startswith(command)]
        log.d(f"Commands for '{string}' = {cmds}")
        return cmds


    def _resolve_alias(self,
                       source: str, default: bool=None,
                       recursive: bool=True, as_string: bool=True) -> Union[str, Tuple[str, str]]:

        def resolve_alias_strict(source_, default_=None):
            target = self._aliases.get(source_, default_)
            if source_ in self._aliases:
                log.d(f"Alias resolved. '{source_}' -> '{target}'")
            return target

        def split_first_space(string, keep_space=False):
            space = string.find(" ")
            if space < 0:
                return string, ""
            return string[:space], string[space+(0 if keep_space else 1):]

        if not recursive:
            return resolve_alias_strict(source, default)

        leading, trailing = "", ""
        resolved = source

        for i in range(Shell.ALIAS_RESOLUTION_MAX_DEPTH):
            x1, x2 = split_first_space(resolved, keep_space=True)
            leading = x1
            trailing = x2 + trailing
            log.d(f"Current resolution: comm='{leading}' suffix='{trailing}'")

            resolved = resolve_alias_strict(leading)

            if not resolved:
                break

            if resolved.startswith(leading + " "):
                log.w("Stopping resolution since target starts with source")
                break

            log.d(f"Resolution: {resolved}")

        if not as_string:
            return leading, trailing

        return f"{leading}{trailing}"

    def _help(self, args: Args) -> NoReturn:
        cmd = args.get_positional(default="usage")
        commands = self._commands_for(cmd, resolve_alias=False)

        ok = False

        target = self._resolve_alias(cmd, recursive=False)
        if target:
            print(f"'{cmd}' alias for '{target}'")
            ok = True
        else:
            log.w("Neither a command nor an alias: '{cmd}'")

        if not ok:
            if commands:
                if len(commands) == 1:
                    command = commands[0]
                    log.d(f"{cmd} resolve into known {command}")
                    ok = command_man(command)
                elif len(commands) > 1:
                    print("Available commands: ")
                    for comm in isorted(commands):
                        print(red(cmd) + comm[len(cmd):])
                    ok = True

        if not ok:
            print(f"Can't provide help for '{cmd}'")

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
        return ClientErrors.SUCCESS

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

        print(f"Verbosity = {verbosity} ({_VERBOSITY_EXPLANATION_MAP.get(verbosity, '<unknown>')})")

        return ClientErrors.SUCCESS
