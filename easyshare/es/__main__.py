import sys
from typing import Optional, List, Callable

from easyshare import logging
from easyshare.es.client import Client
from easyshare.es.commands import Commands, is_special_command
from easyshare.es.errors import errcode_string
from easyshare.es.shell import Shell
from easyshare.logging import get_logger
from easyshare.common import DEFAULT_DISCOVER_PORT, APP_NAME_CLIENT_SHORT, APP_VERSION, easyshare_setup, APP_INFO
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.colors import enable_colors
from easyshare.utils.env import is_stdout_terminal
from easyshare.utils.net import is_valid_port
from easyshare.utils.obj import values
from easyshare.utils.pyro.common import enable_pyro_logging
from easyshare.utils.types import is_int, is_str
from easyshare.args import Args as Args, KwArg, INT_PARAM, PRESENCE_PARAM, INT_PARAM_OPT, \
    ArgsParseError, ArgType, ArgsParser, ActionParam

log = get_logger()

# ==================================================================

NON_CLI_COMMANDS = [
    Commands.TRACE, Commands.TRACE_SHORT,       # trace
    Commands.VERBOSE, Commands.VERBOSE_SHORT,   # verbose
    Commands.EXIT,                              # exit
    Commands.QUIT, Commands.QUIT_SHORT          # quit

    # Commands.LOCAL_CHANGE_DIRECTORY,            # cd
    # Commands.REMOTE_CHANGE_DIRECTORY,           # rcd
    # Commands.CLOSE                              # close

    # ^ Not really useful, but who cares ^
]

CLI_COMMANDS = [k for k in values(Commands) if k not in NON_CLI_COMMANDS]


class EsArgs(ArgsParser):
    HELP =          ["-h", "--help"]
    VERSION =       ["-V", "--version"]

    DISCOVER_PORT = ["-d", "--discover-port"]

    VERBOSE =       ["-v", "--verbose"]
    TRACE =         ["-t", "--trace"]

    NO_COLOR =      ["--no-color"]

    def _kwargs_specs(self) -> Optional[List[KwArg]]:
        return [
            (EsArgs.HELP, ActionParam(lambda _: terminate("help"))),
            (EsArgs.VERSION, ActionParam(lambda _: terminate(APP_INFO))),
            (EsArgs.DISCOVER_PORT, INT_PARAM),
            (EsArgs.VERBOSE, INT_PARAM_OPT),
            (EsArgs.TRACE, INT_PARAM_OPT),
            (EsArgs.NO_COLOR, PRESENCE_PARAM),
        ]

    def _continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
        return lambda argname, argtype, idx, args, positionals: argtype != ArgType.VARG

# ==================================================================


def main():
    easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = EsArgs().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort("Parse of arguments failed: {}".format(str(err)))

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    # Verbosity over VERBOSITY_MAX enables pyro logging too
    if args.has_kwarg(EsArgs.VERBOSE):
        log.set_verbosity(args.get_kwarg_param(EsArgs.VERBOSE,
                                               default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_CLIENT_SHORT, APP_VERSION))
    log.i("Starting with arguments\n%s", args)

    verbosity = 0
    tracing = 0
    no_colors = False
    discover_port = DEFAULT_DISCOVER_PORT


    # Colors
    if args.has_kwarg(EsArgs.NO_COLOR):
        no_colors = True

    # Packet tracing
    if args.has_kwarg(EsArgs.TRACE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        tracing = args.get_kwarg_param(
            EsArgs.TRACE,
            default=1
        )

    # Verbosity
    if args.has_kwarg(EsArgs.VERBOSE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        verbosity = args.get_kwarg_param(
            EsArgs.VERBOSE,
            default=logging.VERBOSITY_MAX
        )

    # Discover port
    discover_port = args.get_kwarg_param(
        EsArgs.DISCOVER_PORT,
        default=discover_port
    )

    # Validation

    # - ports

    if not is_valid_port(discover_port):
        abort("Invalid port number {}".format(discover_port))

    # Logging/Tracing/UI setup

    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    if not no_colors and not is_stdout_terminal():
        log.w("Disabling colors since detected non-terminal output file")
        no_colors = True

    enable_colors(not no_colors)

    enable_tracing(tracing)
    if verbosity:
        log.set_verbosity(verbosity)
        enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)


    # Initialize the client
    client = Client(discover_port=discover_port)

    # Initialize the shell as well
    shell = Shell(client)

    # Check whether
    # 1. Run a command directly from the cli
    # 2. Start an interactive session
    start_shell = True

    # 1. Run a command directly from the cli ?
    vargs = args.get_unparsed_args()
    command = vargs[0] if vargs else None
    if command:
        if command in CLI_COMMANDS or is_special_command(command):
            log.i("Found a valid CLI command '%s'", command)
            command_args = vargs[1:]

            outcome = None

            if shell.has_command(command):
                outcome = shell.execute_shell_command(command, command_args)
            elif client.has_command(command):
                outcome = client.execute_command(command, command_args)
            else:
                abort("Unknown CLI command '{}'".format(command))

            if is_int(outcome) and outcome > 0:
                abort(errcode_string(outcome))
            elif is_str(outcome):
                abort(str)

            # Keep the shell opened only if we performed an 'open'
            # Otherwise close it after the action
            start_shell = client.is_connected_to_server()
        else:
            log.e("Allowed CLI commands are: %s", ", ".join(CLI_COMMANDS))
            abort("Unknown CLI command '{}'".format(command))

    # 2. Start an interactive session ?
    # Actually the shell is started if
    # a) A CLI command opened a connection (open, connect)
    # b) No command has been specified
    if start_shell:
        # Start the shell
        log.i("Starting interactive shell")
        shell.input_loop()


if __name__ == "__main__":
    main()