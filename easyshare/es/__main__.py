import re
import sys
from pathlib import Path
from typing import List, Tuple

from easyshare import logging
from easyshare.args import ArgsParseError
from easyshare.common import DEFAULT_DISCOVER_PORT, APP_NAME_CLIENT, APP_VERSION, easyshare_setup, \
    DEFAULT_DISCOVER_TIMEOUT, APP_INFO, EASYSHARE_RESOURCES_PKG, EASYSHARE_ES_CONF
from easyshare.conf import Conf, INT_VAL, BOOL_VAL, ConfParseError, STR_VAL
from easyshare.es.client import Client
from easyshare.es.shell import Shell
from easyshare.commands.es import Es
from easyshare.logging import get_logger
from easyshare.res.helps import command_usage
from easyshare.styling import enable_styling
from easyshare.tracing import TRACING_NONE, TRACING_TEXT, set_tracing_level
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


class EsrcKeys:
    """ Keys of the .esrc file """
    G_VERBOSE =   "verbose"
    G_TRACE =     "trace"
    G_NO_COLOR =  "no_color"
    G_DISCOVER_PORT = "discover_port"
    G_DISCOVER_WAIT = "discover_wait"
    G_ALIAS = "alias (\S+)"


ESRC_SPEC = {
    # global
    None: {
        EsrcKeys.G_DISCOVER_PORT: INT_VAL,
        EsrcKeys.G_DISCOVER_WAIT: INT_VAL,

        EsrcKeys.G_VERBOSE: INT_VAL,
        EsrcKeys.G_TRACE: INT_VAL,
        EsrcKeys.G_NO_COLOR: BOOL_VAL,

        EsrcKeys.G_ALIAS: STR_VAL,
    },
}



def main():
    # Already called
    # easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = Es().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort(f"Parse of arguments failed: {str(err)}")

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
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

    # Default values
    verbosity = logging.VERBOSITY_NONE
    tracing = TRACING_NONE
    no_colors = False
    discover_port = DEFAULT_DISCOVER_PORT
    discover_wait = DEFAULT_DISCOVER_TIMEOUT
    aliases: List[Tuple[str, str]] = []

    # Config file (.esrc)

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

    if esrc_path.exists():
        try:
            esrc = Conf.parse(
                path=str(esrc_path),
                sections_parsers=ESRC_SPEC,
                comment_prefixes=["#", ";"]
            )
        except ConfParseError as err:
            log.exception(f"Exception occurred while parsing {EASYSHARE_ES_CONF}")
            abort(f"Parse of {EASYSHARE_ES_CONF} file failed: {err}")

        if esrc:
            _, global_section = esrc.global_section()

            log.i(f"{EASYSHARE_ES_CONF} file parsed successfully:\n%s", esrc)

            # Globals

            discover_port = global_section.get(
                EsrcKeys.G_DISCOVER_PORT,
                discover_port
            )

            discover_wait = global_section.get(
                EsrcKeys.G_DISCOVER_WAIT,
                discover_wait
            )

            no_colors = global_section.get(
                EsrcKeys.G_NO_COLOR,
                no_colors
            )

            tracing = global_section.get(
                EsrcKeys.G_TRACE,
                tracing
            )

            verbosity = global_section.get(
                EsrcKeys.G_VERBOSE,
                verbosity
            )

            # Aliases
            for (k, v) in global_section.items():
                match = re.match(EsrcKeys.G_ALIAS, k)
                if not match:
                    continue

                # Found an alias
                target = match.groups()[0]
                source = v
                aliases.append((target, source))
    else:
        log.w(f"No config file found (expect at: '{esrc_path.absolute()}')")

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

    enable_styling(are_colors_supported() and not no_colors)
    logging.init_logging() # update colors

    set_tracing_level(tracing)

    if verbosity:
        log.set_verbosity(verbosity)


    # Initialize the client
    client = Client(discover_port=discover_port,
                    discover_timeout=discover_wait)

    # Initialize the shell as well
    shell = Shell(client)

    # Add the aliases, if any
    for (source, target) in aliases:
        shell.add_alias(source, target)

    # Check whether
    # 1. Run a command directly from the cli
    # 2. Start an interactive session
    start_shell = True

    # 1. Run a command directly from the cli ?
    pargs = args.get_unparsed_args()

    if pargs:
        shell.execute(lexer.join(pargs, quote_char=None))

        # Keep the shell opened only if we performed an 'open'
        # Otherwise close it after the action
        start_shell = client.is_connected_to_server()

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
    command_usage(Es.name())
    terminate()


if __name__ == "__main__":
    main()