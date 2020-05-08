import socket
import sys
from typing import List, Optional, Callable

from easyshare import logging
from easyshare.args import KwArgSpec, ParamsSpec, INT_PARAM, INT_PARAM_OPT, PRESENCE_PARAM, STR_PARAM, ArgsParseError, \
    ArgType
from easyshare.client.args import ArgsParser, PositionalArgs
from easyshare.conf import Conf, INT_VAL, STR_VAL, BOOL_VAL, ConfParseError
from easyshare.logging import get_logger
from easyshare.passwd.auth import AuthFactory
from easyshare.server.server import Server
from easyshare.server.sharing import Sharing
from easyshare.shared.args import Args
from easyshare.shared.common import APP_VERSION, APP_NAME_SERVER_SHORT, SERVER_NAME_ALPHABET, easyshare_setup
from easyshare.ssl import get_ssl_context
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.utils.colors import enable_colors
from easyshare.utils.net import is_valid_port
from easyshare.utils.pyro import enable_pyro_logging
from easyshare.utils.ssl import create_server_ssl_context
from easyshare.utils.str import satisfy
from easyshare.utils.asserts import assert_true
# ==================================================================
from easyshare.utils.types import to_int

log = get_logger()


# === HELPS ===

HELP_APP = """easyshare deamon (esd)
...
"""


# === ARGUMENTS ===

class SharingArgs(PositionalArgs):
    READ_ONLY = ["-r", "--read-only"]

    def __init__(self):
        super().__init__(1, 1)

    def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
        return [
            KwArgSpec(SharingArgs.READ_ONLY, PRESENCE_PARAM),
        ]

class EsdArgs(ArgsParser):
    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    CONFIG = ["-c", "--config"]

    NAME = ["-n", "--name"]
    ADDRESS = ["-a", "--address"]
    PORT = ["-p", "--port"]
    DISCOVER_PORT = ["-d", "--discover-port"]
    PASSWORD = ["-P", "--password"]

    VERBOSE =   ["-v", "--verbose"]
    TRACE =     ["-t", "--trace"]
    NO_COLOR =  ["--no-color"]

    def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
        return [
            KwArgSpec(EsdArgs.HELP,
                      ParamsSpec(0, 0, lambda _: terminate("help"))),
            KwArgSpec(EsdArgs.VERSION,
                      ParamsSpec(0, 0, lambda _: terminate("version"))),

            KwArgSpec(EsdArgs.CONFIG, STR_PARAM),

            KwArgSpec(EsdArgs.NAME, STR_PARAM),
            KwArgSpec(EsdArgs.ADDRESS, STR_PARAM),
            KwArgSpec(EsdArgs.PORT, INT_PARAM),
            KwArgSpec(EsdArgs.DISCOVER_PORT, INT_PARAM),
            KwArgSpec(EsdArgs.PASSWORD, STR_PARAM),

            KwArgSpec(EsdArgs.VERBOSE, INT_PARAM_OPT),
            KwArgSpec(EsdArgs.TRACE, INT_PARAM_OPT),
            KwArgSpec(EsdArgs.NO_COLOR, PRESENCE_PARAM),

        ]

    # def _continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
    #     return lambda argname, argtype, idx, args, positionals: argtype != ArgType.VARG

class EsdConfKeys:
    G_NAME = "name"
    G_ADDRESS = "address"
    G_PORT = "port"
    G_DISCOVER_PORT = "discover_port"
    G_PASSWORD = "password"
    G_SSL = "ssl"
    G_SSL_CERT = "ssl_cert"
    G_SSL_PRIVKEY = "ssl_privkey"

    G_VERBOSE =   "verbose"
    G_TRACE =     "trace"
    G_NO_COLOR =  "no_color"

    S_PATH = "path"
    S_READONLY = "readonly"

ESD_CONF_SPEC = {
    None: {
        EsdConfKeys.G_NAME: STR_VAL,
        EsdConfKeys.G_ADDRESS: STR_VAL,
        EsdConfKeys.G_PORT: INT_VAL,
        EsdConfKeys.G_DISCOVER_PORT: INT_VAL,
        EsdConfKeys.G_PASSWORD: STR_VAL,
        EsdConfKeys.G_SSL: BOOL_VAL,
        EsdConfKeys.G_SSL_CERT: STR_VAL,
        EsdConfKeys.G_SSL_PRIVKEY: STR_VAL,

        EsdConfKeys.G_VERBOSE: INT_VAL,
        EsdConfKeys.G_TRACE: INT_VAL,
        EsdConfKeys.G_NO_COLOR: BOOL_VAL,
    },
    "^\\[([a-zA-Z0-9_]+)\\]$": {
        EsdConfKeys.S_PATH: STR_VAL,
        EsdConfKeys.S_READONLY: BOOL_VAL,
    }
}


# ==================================================================


def main():
    import logging as pylogging

    easyshare_setup()

    if len(sys.argv) <= 1:
        terminate(HELP_APP)

    # Parse arguments
    g_args = None

    try:
        g_args = EsdArgs().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort("Parse of global arguments failed: {}".format(str(err)))

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    # Verbosity over VERBOSITY_MAX enables pyro logging too
    if g_args.has_kwarg(EsdArgs.VERBOSE):
        log.set_verbosity(g_args.get_kwarg_param(EsdArgs.VERBOSE,
                                                 default=logging.VERBOSITY_MAX + 1))

    log.i("{} v. {}".format(APP_NAME_SERVER_SHORT, APP_VERSION))
    log.i("Starting with arguments\n%s", g_args)

    # Default values
    verbosity = 0
    tracing = 0
    no_colors = False

    server_name = socket.gethostname()
    server_address = None
    server_port = None
    server_discover_port = None
    server_password = None
    server_ssl_enabled = False
    server_ssl_cert = None
    server_ssl_privkey = None

    # Config file

    sharings = {}

    def add_sharing(path: str, name: str, readonly: bool):
        if not path:
            log.w("Invalid path for sharing '%s'; skipping it")
            return

        sh = Sharing.create(
            name=name,
            path=path,
            read_only=readonly
        )

        if not sh:
            log.w("Invalid or incomplete sharing config; skipping it")
            return

        sharings[name] = sh

    # Take out config settings

    if EsdArgs.CONFIG in g_args:
        cfg = None

        try:
            cfg = Conf.parse(
                path=g_args.get_kwarg_param(EsdArgs.CONFIG),
                sections_parsers=ESD_CONF_SPEC,
                comment_prefixes=["#", ";"]
            )
        except ConfParseError as err:
            log.exception("Exception occurred while parsing conf")
            abort("Parse of config file failed: {}".format(str(err)))

        if cfg:
            log.i("Config file parsed successfully:\n%s", cfg)

            # Config's global settings

            server_name = cfg.get_global_value(
                EsdConfKeys.G_NAME,
                default=server_name
            )

            server_address = cfg.get_global_value(
                EsdConfKeys.G_ADDRESS,
                default=server_address
            )

            server_port = cfg.get_global_value(
                EsdConfKeys.G_PORT,
                default=server_port
            )

            server_discover_port = cfg.get_global_value(
                EsdConfKeys.G_DISCOVER_PORT,
                default=server_discover_port
            )

            server_password = cfg.get_global_value(
                EsdConfKeys.G_PASSWORD,
                default=server_password
            )

            server_ssl_cert = cfg.get_global_value(
                EsdConfKeys.G_SSL_CERT,
                default=server_ssl_cert
            )
            server_ssl_privkey = cfg.get_global_value(
                EsdConfKeys.G_SSL_PRIVKEY,
                default=server_ssl_privkey
            )

            server_ssl_enabled = cfg.get_global_value(
                EsdConfKeys.G_SSL,
                default=server_ssl_cert and server_ssl_privkey
            )

            no_colors = cfg.get_global_value(
                EsdConfKeys.G_NO_COLOR,
                default=no_colors
            )

            tracing = cfg.get_global_value(
                EsdConfKeys.G_TRACE,
                default=tracing
            )

            verbosity = cfg.get_global_value(
                EsdConfKeys.G_VERBOSE,
                default=verbosity
            )

            # Config's sharings

            for s_name, s_settings in cfg.get_non_global_sections().items():
                s_path = s_settings.get(EsdConfKeys.S_PATH)
                s_readonly = s_settings.get(EsdConfKeys.S_PATH, False)

                add_sharing(path=s_path, name=s_name, readonly=s_readonly)

    # Args from command line: eventually overwrite config settings

    # Name
    server_name = g_args.get_kwarg_param(
        EsdArgs.NAME,
        default=server_name
    )

    # Server address
    server_address = g_args.get_kwarg_param(
        EsdArgs.ADDRESS,
        default=server_address
    )

    # Server port
    server_port = g_args.get_kwarg_param(
        EsdArgs.PORT,
        default=server_port
    )

    # Discover port
    server_discover_port = g_args.get_kwarg_param(
        EsdArgs.DISCOVER_PORT,
        default=server_discover_port
    )

    # Password
    server_password = g_args.get_kwarg_param(
        EsdArgs.PASSWORD,
        default=server_password
    )

    # Colors
    if g_args.has_kwarg(EsdArgs.NO_COLOR):
        no_colors = True

    # Packet tracing
    if g_args.has_kwarg(EsdArgs.TRACE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        tracing = g_args.get_kwarg_param(
            EsdArgs.TRACE,
            default=1
        )

    # Verbosity
    if g_args.has_kwarg(EsdArgs.VERBOSE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        verbosity = g_args.get_kwarg_param(
            EsdArgs.VERBOSE,
            default=logging.VERBOSITY_MAX
        )

    # Validation

    # - server name
    if not satisfy(server_name, SERVER_NAME_ALPHABET):
        abort("Invalid server name: '{}'".format(server_name))

    # - ports
    for p in [server_port, server_discover_port]:
        if p and not is_valid_port(p) and p != -1:
            abort("Invalid port number {}".format(p))

    # Logging/Tracing/UI setup

    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    enable_colors(not no_colors)
    enable_tracing(tracing)
    if verbosity:
        log.set_verbosity(verbosity)
        enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)

    # Parse sharing arguments (only a sharing is allowed in the cli)

    vargs = g_args.get_vargs()
    if vargs:
        log.d("Found %d positional args: considering those sharing args", len(vargs))

        s_args = None

        try:
            s_args = SharingArgs().parse(vargs)
        except ArgsParseError as err:
            log.exception("Exception occurred while parsing args")
            abort("Parse of sharing arguments failed: {}".format(str(err)))

        s_vargs = s_args.get_vargs()

        log.d("Sharing len(args): %d", len(s_vargs))

        if s_vargs: # should always be valid actually
            s_path = s_vargs[0]
            s_name = s_vargs[1] if len(s_vargs) >= 2 else None
            s_readonly = s_args.get_kwarg_param(SharingArgs.READ_ONLY,
                                                default=False)

            add_sharing(path=s_path, name=s_name, readonly=s_readonly)


    # SSL

    ssl_context = None
    if server_ssl_enabled:
        if server_ssl_cert and server_ssl_privkey:
            log.i("Creating SSL context")
            log.i("SSL cert path: %s", server_ssl_cert)
            log.i("SSL privkey path: %s", server_ssl_privkey)
            ssl_context = create_server_ssl_context(
                cert=server_ssl_cert, privkey=server_ssl_privkey)
        else:
            if not server_ssl_cert:
                log.w("ssl=true, but ssl_cert has not been specified; disabling ssl")

            if not server_ssl_privkey:
                log.w("ssl=true, but ssl_privkey has not been specified; disabling ssl")

    # Configure server and add sharings to it

    auth = AuthFactory.parse(server_password)

    log.i("Required server name: %s", server_name)
    log.i("Required server address: %s", server_address)
    log.i("Required server port: %s", str(server_port))
    log.i("Required server discover port: %s", str(server_discover_port))
    log.i("Required auth: %s", auth.algo_type())


    server = Server(
        name=server_name,
        address=server_address,
        port=server_port,
        discover_port=server_discover_port,
        auth=AuthFactory.parse(server_password),
        ssl_context=ssl_context
    )

    print("Server name:    ", server.name())
    print("Server auth:    ", server.auth_type())
    print("Server address: ", server.endpoint()[0])
    print("Server port:    ", server.endpoint()[1])
    print("Discover port:  ", server._discover_daemon.endpoint()[1] if server.is_discoverable() else "DISABLED")
    print("SSL:            ", True if get_ssl_context() else False)
    print("------------------------")

    if sharings:
        # Add every sharing to the server
        for sharing in sharings.values():
            print("* " + sharing.name + " --> " + sharing.path)
            server.add_sharing(sharing)
        print("------------------------")
    else:
        log.w("No sharings found, it will be an empty server")

    print("STARTED")
    server.start()


if __name__ == "__main__":
    main()
