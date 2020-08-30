import sys
from pathlib import Path

from easyshare import logging
from easyshare.args import ArgsParseError
from easyshare.common import DEFAULT_DISCOVER_PORT, APP_NAME_CLIENT, APP_VERSION, easyshare_setup, \
    DEFAULT_DISCOVER_WAIT, APP_INFO, EASYSHARE_RESOURCES_PKG, EASYSHARE_ES_CONF, TRACING_NONE, TRACING_TEXT
from easyshare.es.client import Client
from easyshare.es.shell import Shell
from easyshare.commands.es import Es, EsUsage
from easyshare.logging import get_logger
from easyshare.res.helps import command_usage
from easyshare.settings import set_setting, Settings, get_setting
from easyshare.styling import enable_styling
from easyshare.utils import abort, terminate, lexer
from easyshare.utils.env import is_stdout_terminal, are_colors_supported
from easyshare.utils.net import is_valid_port


# if __name__ == "__main__":

# Call it now before get_logger for enable colors properly
# and let logger be initialized with/without colors
from easyshare.utils.resources import read_resource_string

easyshare_setup()


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


# ==================================================================

#
# class EsrcKeys:
#     """ Keys of the .esrc file """
#     G_VERBOSE =   "verbose"
#     G_TRACE =     "trace"
#     G_NO_COLOR =  "no_color"
#     G_DISCOVER_PORT = "discover_port"
#     G_DISCOVER_WAIT = "discover_wait"
#     G_SHELL_PASSTHROUGH = "shell"
#     G_KEEP_OPEN = "keep_open"
#     G_ALIAS = "alias (\S+)"

#
# ESRC_SPEC = {
#     # global
#     None: {
#         EsrcKeys.G_DISCOVER_PORT: INT_VAL,
#         EsrcKeys.G_DISCOVER_WAIT: INT_VAL,
#
#         EsrcKeys.G_VERBOSE: INT_VAL,
#         EsrcKeys.G_TRACE: INT_VAL,
#         EsrcKeys.G_NO_COLOR: BOOL_VAL,
#
#         EsrcKeys.G_SHELL_PASSTHROUGH: BOOL_VAL,
#         EsrcKeys.G_KEEP_OPEN: BOOL_VAL,
#
#         EsrcKeys.G_ALIAS: STR_VAL,
#     },
# }
#


def main():
    # Already called
    # easyshare_setup()

    # Default settings
    set_setting(Settings.TRACING, TRACING_NONE)
    set_setting(Settings.VERBOSITY, logging.VERBOSITY_NONE)
    set_setting(Settings.DISCOVER_PORT, DEFAULT_DISCOVER_PORT)
    set_setting(Settings.DISCOVER_WAIT, DEFAULT_DISCOVER_WAIT)
    set_setting(Settings.SHELL_PASSTHROUGH, False)
    set_setting(Settings.COLORS, False)

    # Parse arguments
    args = None

    try:
        args = Es().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort(f"parse of arguments failed: {str(err)}")

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    if args.has_option(Es.VERBOSE):
        set_setting(Settings.VERBOSITY,
                    args.get_option_param(Es.VERBOSE, default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_CLIENT, APP_VERSION))
    log.i("Starting with arguments\n%s", args)

    # Help?
    if Es.HELP in args:
        _print_usage_and_quit()

    # Version?
    if Es.VERSION in args:
        terminate(APP_INFO)

    # Default values
    verbosity = get_setting(Settings.VERBOSITY)
    tracing = get_setting(Settings.TRACING)
    no_colors = get_setting(Settings.COLORS)
    shell_passthrough = get_setting(Settings.SHELL_PASSTHROUGH)
    discover_port = get_setting(Settings.DISCOVER_PORT)
    discover_wait = get_setting(Settings.DISCOVER_WAIT)

    keep_open = False

    # Create config file (.esrc) if not exists

    esrc_path = Path.home() / EASYSHARE_ES_CONF

    if not esrc_path.exists():
        try:
            log.d(f"Creating default {EASYSHARE_ES_CONF}")

            default_esrc_content = read_resource_string(
                EASYSHARE_RESOURCES_PKG, EASYSHARE_ES_CONF)

            log.d(default_esrc_content)

            esrc_path.write_text(default_esrc_content)
        except Exception:
            log.w(f"Failed to write default {EASYSHARE_ES_CONF} file")

    # Colors
    if Es.NO_COLOR in args:
        no_colors = True

    # Packet tracing
    if Es.TRACE in args:
        # The param of -t is optional:
        # if not specified the default is TEXT
        tracing = args.get_option_param(
            Es.TRACE,
            default=TRACING_TEXT
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

    # Discover timeout
    discover_wait = args.get_option_param(
        Es.DISCOVER_TIMEOUT,
        default=discover_wait
    )

    # Shell passthrough
    shell_passthrough = args.get_option_param(
        Es.SHELL_PASSTHROUGH,
        default=shell_passthrough
    )

    # Keep open
    keep_open = args.get_option_param(
        Es.KEEP_OPEN,
        default=keep_open
    )

    # Validation

    # - ports

    if not is_valid_port(discover_port):
        abort("invalid port number {}".format(discover_port))

    # Logging/Tracing/UI setup

    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    if not no_colors and not is_stdout_terminal():
        log.w("Disabling colors since detected non-terminal output file")
        no_colors = True

    enable_styling(are_colors_supported() and not no_colors)
    logging.init_logging() # update colors

    set_setting(Settings.TRACING, tracing)

    if verbosity:
        set_setting(Settings.VERBOSITY, verbosity)

    # Initialize the client
    client = Client(discover_port=discover_port,
                    discover_timeout=discover_wait)

    # Initialize the shell as well
    shell = Shell(client, passthrough=shell_passthrough)

    # Check whether
    # 1. Run a command directly from the cli
    # 2. Start an interactive session

    # 1. Run a command directly from the cli ?
    pargs = args.get_unparsed_args()

    if pargs:
        shell.execute(lexer.join(pargs, quote_char=None))

        # Keep the shell opened only if we performed an 'open' or -k (keep_open)
        # is given.
        # Otherwise close it after the action
        keep_open = keep_open or client.is_connected_to_server()
    else:
        keep_open = True

    # 2. Start an interactive session ?
    # Actually the shell is started if
    # a) A CLI command opened a connection (open, connect)
    # b) No command has been specified
    if keep_open:
        # Start the shell
        log.i("Starting interactive shell")
        shell.input_loop()


def _print_usage_and_quit():
    """ Prints the es usage and exit """
    command_usage(EsUsage.helpname())
    terminate()


if __name__ == "__main__":
    main()