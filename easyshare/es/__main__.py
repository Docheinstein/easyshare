import sys

from Pyro5.errors import PyroError

from easyshare import logging
from easyshare.es.client import Client
from easyshare.helps.commands import Commands, is_special_command
from easyshare.es.errors import errno_str
from easyshare.es.shell import Shell
from easyshare.helps.es import Es
from easyshare.logging import get_logger
from easyshare.common import DEFAULT_DISCOVER_PORT, APP_NAME_CLIENT, APP_VERSION, easyshare_setup, \
    DEFAULT_DISCOVER_TIMEOUT, APP_INFO
from easyshare.res.helps import get_command_usage
from easyshare.tracing import enable_tracing
from easyshare.utils import abort, terminate
from easyshare.styling import enable_colors
from easyshare.utils.env import is_stdout_terminal, are_colors_supported
from easyshare.utils.net import is_valid_port
from easyshare.utils.obj import values
from easyshare.utils.pyro import enable_pyro_logging
from easyshare.utils.types import is_int, is_str
from easyshare.args import ArgsParseError


log = get_logger(__name__)


# ==================================
# ===== ENTRY POINT OF ES ==========
# ==================================

# SYNOPSIS
# es OPTION... [[COMMAND] [COMMAND_OPTIONS]]
#
# OPTIONS
# -d, --discover-port  port      port used for broadcast discovery messages
# -h, --help                     show this help
# --no-color                     don't print ANSI escape characters
# -t, --trace  0_or_1            enable/disable tracing
# -v, --verbose  level           set verbosity level
# -V, --version                  show the easyshare version
# -w, --discover-wait  seconds   time to wait for discovery responses


NON_CLI_COMMANDS = [
    Commands.TRACE, Commands.TRACE_SHORT,       # trace
    Commands.VERBOSE, Commands.VERBOSE_SHORT,   # verbose
    Commands.EXIT,                              # exit
    Commands.QUIT, Commands.QUIT_SHORT          # quit

    # Commands.LOCAL_CHANGE_DIRECTORY,            # cd
    # Commands.REMOTE_CHANGE_DIRECTORY,           # rcd
    # Commands.CLOSE                              # close

    # ^ Not really useful, but we can leave these anyway ^
]

CLI_COMMANDS = [k for k in values(Commands) if k not in NON_CLI_COMMANDS]



# ==================================================================


def main():
    easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = Es().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort("Parse of arguments failed: {}".format(str(err)))

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    # Verbosity over VERBOSITY_MAX enables pyro logging too
    if args.has_option(Es.VERBOSE):
        log.set_verbosity(args.get_option_param(Es.VERBOSE,
                                                default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_CLIENT, APP_VERSION))
    log.i("Starting with arguments\n%s", args)

    # Help?
    if Es.HELP in args:
        _print_usage_and_quit()

    # Version?
    if Es.VERSION in args:
        terminate(APP_INFO)

    verbosity = 0
    tracing = 0
    no_colors = False
    discover_port = DEFAULT_DISCOVER_PORT
    discover_timeout = DEFAULT_DISCOVER_TIMEOUT

    # Colors
    if Es.NO_COLOR in args:
        no_colors = True

    # Packet tracing
    if Es.TRACE in args:
        # The param of -v is optional:
        # if not specified the default is DEBUG
        tracing = args.get_option_param(
            Es.TRACE,
            default=1
        )

    # Verbosity
    if Es.VERBOSE in args:
        # The param of -v is optional:
        # if not specified the default is DEBUG
        verbosity = args.get_option_param(
            Es.VERBOSE,
            default=logging.VERBOSITY_MAX
        )

    # Discover port
    discover_port = args.get_option_param(
        Es.DISCOVER_PORT,
        default=discover_port
    )

    # Discover port
    discover_timeout = args.get_option_param(
        Es.DISCOVER_TIMEOUT,
        default=discover_timeout
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

    enable_colors(are_colors_supported() and not no_colors)

    enable_tracing(tracing)
    if verbosity:
        log.set_verbosity(verbosity)
        enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)


    # Initialize the client
    client = Client(discover_port=discover_port,
                    discover_timeout=discover_timeout)

    # Initialize the shell as well
    shell = Shell(client)

    # Check whether
    # 1. Run a command directly from the cli
    # 2. Start an interactive session
    start_shell = True

    # 1. Run a command directly from the cli ?
    pargs = args.get_unparsed_args()
    command = pargs[0] if pargs else None
    if command:
        if command in CLI_COMMANDS or is_special_command(command):
            log.i("Found a valid CLI command '%s'", command)
            command_args = pargs[1:]

            outcome = None

            # TODO: use the shell wrapper in some way
            raise ValueError("NOT IMPL")
            # try:
            #     if shell.has_command(command):
            #         outcome = shell.execute_shell_command(command, command_args)
            #     elif client.has_command(command):
            #         outcome = client.execute_command(command, command_args)
            #     else:
            #         abort("Unknown CLI command '{}'".format(command))
            # except PyroError as pyroerr:
            #     log.exception("Pyro error occurred %s", pyroerr)
            #     print_error(ClientErrors.CONNECTION_ERROR)
            # except KeyboardInterrupt:
            #     log.d("\nCTRL+C")


            if is_int(outcome) and outcome > 0:
                abort(errno_str(outcome))
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



def _print_usage_and_quit():
    """ Prints the es usage and exit """
    es_usage = get_command_usage(Es.name())

    if not es_usage:
        # Something went wrong with the dynamic loading of the usage
        abort(f"Can't provide usage of '{Es.name()}'")

    terminate(es_usage)


if __name__ == "__main__":
    main()