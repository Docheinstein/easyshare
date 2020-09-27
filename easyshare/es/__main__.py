import sys
from pathlib import Path

from easyshare import logging
from easyshare.args import ArgsParseError
from easyshare.commands.es import Es, EsUsage
from easyshare.common import APP_NAME_CLIENT, APP_VERSION, easyshare_setup, \
    APP_INFO, EASYSHARE_RESOURCES_PKG, EASYSHARE_ES_CONF, TRACING_TEXT, VERBOSITY_MAX
from easyshare.es.client import Client
from easyshare.es.shell import Shell
from easyshare.logging import get_logger
from easyshare.res.helps import command_usage
from easyshare.settings import set_setting, Settings, get_setting
from easyshare.utils import abort, terminate, lexer
from easyshare.utils.env import is_stdout_terminal, is_styling_supported
from easyshare.utils.net import is_valid_port
# Call it now before get_logger for enable colors properly
# and let logger be initialized with/without colors
from easyshare.utils.resources import read_resource_string

# if __name__ == "__main__":

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

def main():
    # Already called: easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = Es().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.eexception("Exception occurred while parsing args")
        abort(f"parse of arguments failed: {str(err)}")

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    if args.has_option(Es.VERBOSE):
        set_setting(Settings.VERBOSITY,
                    args.get_option_param(Es.VERBOSE, default=VERBOSITY_MAX))

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
    colors = get_setting(Settings.COLORS)
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
        colors = False

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
            default=VERBOSITY_MAX
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
    if colors and not is_stdout_terminal():
        log.w("Disabling colors since detected non-terminal output file")
        colors = False

    log.d("Colors: %s", colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    # Set settings
    set_setting(Settings.COLORS, is_styling_supported() and colors)
    set_setting(Settings.TRACING, tracing)
    set_setting(Settings.VERBOSITY, verbosity)
    set_setting(Settings.DISCOVER_PORT, discover_port)
    set_setting(Settings.DISCOVER_WAIT, discover_wait)
    set_setting(Settings.SHELL_PASSTHROUGH, shell_passthrough)

    # Initialize the client
    client = Client()

    # Initialize the shell as well
    shell = Shell(client)

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