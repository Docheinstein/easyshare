import os
import sys
from typing import Optional, List, Callable

from easyshare import logging
from easyshare.client.args import ArgsParser
from easyshare.client.client import Client
from easyshare.client.commands import Commands, is_special_command
from easyshare.client.errors import errcode_string
from easyshare.client.shell import Shell
from easyshare.logging import get_logger
from easyshare.shared.common import DEFAULT_DISCOVER_PORT, APP_NAME_CLIENT_SHORT, APP_VERSION, ENV_EASYSHARE_VERBOSITY, \
    easyshare_setup
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.utils.colors import enable_colors
from easyshare.utils.math import rangify
from easyshare.utils.obj import values
from easyshare.utils.types import to_int, is_int, is_str
from easyshare.args import Args as Args, KwArgSpec, ParamsSpec, INT_PARAM, PRESENCE_PARAM, INT_PARAM_OPT, ArgsParseError

log = get_logger()

# ==================================================================

NON_CLI_COMMANDS = [
    Commands.TRACE, Commands.TRACE_SHORT,       # trace
    Commands.VERBOSE, Commands.VERBOSE_SHORT,   # verbose
    Commands.LOCAL_CHANGE_DIRECTORY,            # cd
    Commands.REMOTE_CHANGE_DIRECTORY,           # rcd
    Commands.CLOSE                              # close
]

CLI_COMMANDS = [k for k in values(Commands) if k not in NON_CLI_COMMANDS]


class EsArgs(ArgsParser):
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]

    PORT =      ["-p", "--port"]
    WAIT =      ["-w", "--wait"]

    VERBOSE =   ["-v", "--verbose"]
    TRACE =     ["-t", "--trace"]

    NO_COLOR =  ["--no-color"]

    def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
        return [
            KwArgSpec(EsArgs.HELP,
                      ParamsSpec(0, 0, lambda _: terminate("help"))),
            KwArgSpec(EsArgs.VERSION,
                      ParamsSpec(0, 0, lambda _: terminate("version"))),
            KwArgSpec(EsArgs.PORT, INT_PARAM),
            KwArgSpec(EsArgs.WAIT, INT_PARAM),
            KwArgSpec(EsArgs.VERBOSE, INT_PARAM_OPT),
            KwArgSpec(EsArgs.TRACE, INT_PARAM_OPT),
            KwArgSpec(EsArgs.NO_COLOR, PRESENCE_PARAM),
        ]

    def _continue_parsing_hook(self) -> Optional[Callable[[str, int, 'Args', List[str]], bool]]:
        return lambda argname, idx, args, positionals: not positionals

# ==================================================================


def main():
    easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = EsArgs().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort("Parse of global arguments failed: {}".format(str(err)))

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    if args.has_kwarg(EsArgs.VERBOSE):
        log.set_verbosity(args.get_kwarg_param(EsArgs.VERBOSE,
                                               default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_CLIENT_SHORT, APP_VERSION))
    log.i("Starting with arguments\n%s", args)

    verbosity = 0
    tracing = 0
    no_colors = False

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

    # Logging/Tracing/UI setup

    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    enable_colors(not no_colors)
    enable_tracing(tracing)
    if verbosity:
        log.set_verbosity(verbosity)


    # Initialize client
    client = Client(discover_port=args.get_kwarg_param(EsArgs.PORT, DEFAULT_DISCOVER_PORT))

    # Check whether
    # 1. Run a command directly from the cli
    # 2. Start an interactive session

    start_shell = True

    # 1. Run a command directly from the cli ?
    vargs = args.get_vargs()
    command = vargs[0] if vargs else None
    if command:
        if command in CLI_COMMANDS or is_special_command(command):
            log.i("Found a valid CLI command '%s'", command)
            command_args = args.get_unparsed_args([])
            outcome = client.execute_command(command, command_args)

            if is_int(outcome) and outcome > 0:
                abort(errcode_string(outcome))
            elif is_str(outcome):
                abort(str)

            # Keep the shell opened only if we performed an 'open'
            # Otherwise close it after the action
            start_shell = (command == Commands.OPEN)
        else:
            log.w("Invalid CLI command '%s'; ignoring it and starting shell", command)
            log.w("Allowed CLI commands are: %s", ", ".join(CLI_COMMANDS))

            start_shell = False

    # 2. Start an interactive session ?
    if start_shell:
        # Start the shell
        log.i("Starting interactive shell")
        shell = Shell(client)
        shell.input_loop()


if __name__ == "__main__":
    main()
