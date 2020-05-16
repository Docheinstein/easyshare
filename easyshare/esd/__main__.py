import socket
import sys
from typing import List, Optional

from easyshare.esd.common import Sharing

from easyshare import logging, args
from easyshare.args import Kwarg, INT_PARAM, INT_PARAM_OPT, PRESENCE_PARAM, STR_PARAM, ArgsParseError, \
    Pargs, ArgsParser, ActionParam
from easyshare.conf import Conf, INT_VAL, STR_VAL, BOOL_VAL, ConfParseError
from easyshare.esd.daemons.discover import get_discover_daemon
from easyshare.esd.daemons.transfer import get_transfer_daemon
from easyshare.help.esd import Esd
from easyshare.logging import get_logger
from easyshare.auth import AuthFactory
from easyshare.esd.server import Server
from easyshare.common import APP_VERSION, APP_NAME_SERVER_SHORT, SERVER_NAME_ALPHABET, easyshare_setup, APP_INFO
from easyshare.res.helps import get_command_man, get_command_usage
from easyshare.ssl import get_ssl_context
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.styling import enable_colors, bold
from easyshare.utils.env import are_colors_supported
from easyshare.utils.net import is_valid_port
from easyshare.utils.pyro import enable_pyro_logging
from easyshare.utils.ssl import create_server_ssl_context
from easyshare.utils.str import satisfy

# ==================================================================

log = get_logger(__name__)


# === ARGUMENTS ===

class SharingArgs(Pargs):
    READ_ONLY = ["-r", "--read-only"]

    def __init__(self):
        super().__init__(1, 1)

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.READ_ONLY, PRESENCE_PARAM),
        ]
# 
# class Esd(ArgsParser):
#     HELP = ["-h", "--help"]
#     VERSION = ["-V", "--version"]
# 
#     CONFIG = ["-c", "--config"]
# 
#     NAME = ["-n", "--name"]
#     ADDRESS = ["-a", "--address"]
#     PORT = ["-p", "--port"]
#     DISCOVER_PORT = ["-d", "--discover-port"]
#     PASSWORD = ["-P", "--password"]
# 
#     SSL_CERT = ["--ssl-cert"]
#     SSL_PRIVKEY = ["--ssl-privkey"]
#     REXEC = ["-e", "--rexec"]
# 
#     VERBOSE =   ["-v", "--verbose"]
#     TRACE =     ["-t", "--trace"]
#     NO_COLOR =  ["--no-color"]
# 
#     def kwargs_specs(self) -> Optional[List[Kwarg]]:
#         return [
#             (Esd.HELP, ActionParam(lambda _: terminate("help"))),
#             (Esd.VERSION, ActionParam(lambda _: terminate("version"))),
# 
#             (Esd.CONFIG, STR_PARAM),
# 
#             (Esd.NAME, STR_PARAM),
#             (Esd.ADDRESS, STR_PARAM),
#             (Esd.PORT, INT_PARAM),
#             (Esd.DISCOVER_PORT, INT_PARAM),
#             (Esd.PASSWORD, STR_PARAM),
#             (Esd.SSL_CERT, STR_PARAM),
#             (Esd.SSL_PRIVKEY, STR_PARAM),
# 
#             (Esd.REXEC, PRESENCE_PARAM),
# 
#             (Esd.VERBOSE, INT_PARAM_OPT),
#             (Esd.TRACE, INT_PARAM_OPT),
#             (Esd.NO_COLOR, PRESENCE_PARAM),
# 
#         ]

    # def _continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, 'Args', List[str]], bool]]:
    #     return lambda argname, argtype, idx, args, positionals: argtype != ArgType.PARG

class EsdConfKeys:
    G_NAME = "name"
    G_ADDRESS = "address"
    G_PORT = "port"
    G_DISCOVER_PORT = "discover_port"
    G_PASSWORD = "password"
    G_SSL = "ssl"
    G_SSL_CERT = "ssl_cert"
    G_SSL_PRIVKEY = "ssl_privkey"
    G_REXEC = "rexec"

    G_VERBOSE =   "verbose"
    G_TRACE =     "trace"
    G_NO_COLOR =  "no_color"

    S_PATH = "path"
    S_READONLY = "readonly"

ESD_CONF_SPEC = {
    # global esd settings
    None: {
        EsdConfKeys.G_NAME: STR_VAL,
        EsdConfKeys.G_ADDRESS: STR_VAL,
        EsdConfKeys.G_PORT: INT_VAL,
        EsdConfKeys.G_DISCOVER_PORT: INT_VAL,
        EsdConfKeys.G_PASSWORD: STR_VAL,
        EsdConfKeys.G_SSL: BOOL_VAL,
        EsdConfKeys.G_SSL_CERT: STR_VAL,
        EsdConfKeys.G_SSL_PRIVKEY: STR_VAL,
        EsdConfKeys.G_REXEC: BOOL_VAL,

        EsdConfKeys.G_VERBOSE: INT_VAL,
        EsdConfKeys.G_TRACE: INT_VAL,
        EsdConfKeys.G_NO_COLOR: BOOL_VAL,
    },
    # sharings
    "^\\[([a-zA-Z0-9_]+)\\]$": {
        EsdConfKeys.S_PATH: STR_VAL,
        EsdConfKeys.S_READONLY: BOOL_VAL,
    }
}


# ==================================================================


def main():
    easyshare_setup()

    if len(sys.argv) <= 1:
        terminate(get_command_usage("esd"))

    # Parse arguments
    g_args = None

    try:
        g_args = Esd().parse(sys.argv[1:])
    except ArgsParseError as err:
        log.exception("Exception occurred while parsing args")
        abort("Parse of global arguments failed: {}".format(str(err)))

    # Eventually set verbosity before anything else
    # so that the rest of the startup (config parsing, ...)
    # can be logged
    # Verbosity over VERBOSITY_MAX enables pyro logging too
    if g_args.has_kwarg(Esd.VERBOSE):
        log.set_verbosity(g_args.get_kwarg_param(Esd.VERBOSE,
                                                 default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_SERVER_SHORT, APP_VERSION))
    log.i("Starting with arguments\n%s", g_args)

    # Help?
    if Esd.HELP in g_args:
        terminate(get_command_usage("esd"))

    # Version?
    if Esd.VERSION in g_args:
        terminate(APP_INFO)

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
    server_rexec = False

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

    if Esd.CONFIG in g_args:
        cfg = None

        try:
            cfg = Conf.parse(
                path=g_args.get_kwarg_param(Esd.CONFIG),
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

            server_rexec = cfg.get_global_value(
                EsdConfKeys.G_REXEC,
                default=server_rexec and server_rexec
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
        Esd.NAME,
        default=server_name
    )

    # Server address
    server_address = g_args.get_kwarg_param(
        Esd.ADDRESS,
        default=server_address
    )

    # Server port
    server_port = g_args.get_kwarg_param(
        Esd.PORT,
        default=server_port
    )

    # Discover port
    server_discover_port = g_args.get_kwarg_param(
        Esd.DISCOVER_PORT,
        default=server_discover_port
    )

    # Password
    server_password = g_args.get_kwarg_param(
        Esd.PASSWORD,
        default=server_password
    )

    # SSL cert
    server_ssl_cert = g_args.get_kwarg_param(
        Esd.SSL_CERT,
        default=server_ssl_cert
    )

    # SSL privkey
    server_ssl_privkey = g_args.get_kwarg_param(
        Esd.SSL_PRIVKEY,
        default=server_ssl_privkey
    )

    # SSL enabled: obviously we need both cert and privkey
    # But for now set True if either one of the two is valid
    # will report errors at the end
    server_ssl_enabled = server_ssl_enabled or server_ssl_cert or server_ssl_privkey

    # Rexec
    if g_args.has_kwarg(Esd.REXEC):
        server_rexec = True

    # Colors
    if g_args.has_kwarg(Esd.NO_COLOR):
        no_colors = True

    # Packet tracing
    if g_args.has_kwarg(Esd.TRACE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        tracing = g_args.get_kwarg_param(
            Esd.TRACE,
            default=1
        )

    # Verbosity
    if g_args.has_kwarg(Esd.VERBOSE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        verbosity = g_args.get_kwarg_param(
            Esd.VERBOSE,
            default=logging.VERBOSITY_MAX
        )

    # Validation

    # - esd name
    if not satisfy(server_name, SERVER_NAME_ALPHABET):
        abort("Invalid esd name: '{}'".format(server_name))

    # - ports
    for p in [server_port, server_discover_port]:
        if p and not is_valid_port(p) and p != -1:
            abort("Invalid port number {}".format(p))

    # Logging/Tracing/UI setup

    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    enable_colors(are_colors_supported() and not no_colors)
    enable_tracing(tracing)
    if verbosity:
        log.set_verbosity(verbosity)
        enable_pyro_logging(verbosity > logging.VERBOSITY_MAX)

    # Parse sharing arguments (only a sharing is allowed in the cli)

    pargs = g_args.get_pargs()
    if pargs:
        log.d("Found %d positional args: considering those sharing args", len(pargs))

        s_args = None

        try:
            s_args = SharingArgs().parse(pargs)
        except ArgsParseError as err:
            log.exception("Exception occurred while parsing args")
            abort("Parse of sharing arguments failed: {}".format(str(err)))

        s_pargs = s_args.get_pargs()

        log.d("Sharing len(args): %d", len(s_pargs))

        if s_pargs: # should always be valid actually
            s_path = s_pargs[0]
            s_name = s_pargs[1] if len(s_pargs) >= 2 else None
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
                log.w("ssl_cert not specified; SSL will be disabled")
            if not server_ssl_privkey:
                log.w("ssl_privkey not specified; SSL will be disabled")
            server_ssl_enabled = False

    if not server_ssl_enabled:
        log.w("Server will start in plaintext mode; please consider using SSL")

    # Configure esd and add sharings to it

    auth = AuthFactory.parse(server_password)

    log.i("Required esd name: %s", server_name)
    log.i("Required esd address: %s", server_address)
    log.i("Required esd port: %s", str(server_port))
    log.i("Required esd discover port: %s", str(server_discover_port))
    log.i("Required auth: %s", auth.algo_type())


    server = Server(
        name=server_name,
        address=server_address,
        port=server_port,
        discover_port=server_discover_port,
        auth=AuthFactory.parse(server_password),
        ssl_context=ssl_context,
        rexec=server_rexec
    )

    SEP = "================================"

    SEP_FIRST = SEP + "\n\n"
    SEP_MID = "\n" + SEP + "\n\n"
    SEP_LAST = "\n" + SEP

    # Server info
    s = SEP_FIRST + \
        bold("SERVER INFO") + "\n\n" + \
        "Name:              {}\n".format(server.name()) + \
        "Address:           {}\n".format(server.endpoint()[0]) + \
        "Server port:       {}\n".format(server.endpoint()[1]) + \
        "Transfer port:     {}\n".format(get_transfer_daemon().endpoint()[1]) + \
        "Discover port:     {}\n".format(get_discover_daemon().endpoint()[1] if server.is_discoverable() else "disabeld") + \
        "Auth:              {}\n".format(server.auth_type()) + \
        "SSL:               {}\n".format(True if get_ssl_context() else False) + \
        "Remote execution:  {}\n".format(server.is_rexec_enabled())

    # Sharings
    s += SEP_MID + bold("SHARINGS") + "\n\n"
    for sharing in sharings.values():
        s += "* " + sharing.name + " --> " + sharing.path + "\n"
    s += SEP_MID

    s += bold("RUNNING...") + "\n"

    if sharings:
        # Add every sharing to the esd
        for sharing in sharings.values():
            server.add_sharing(sharing)
    else:
        log.w("No sharings found, it will be an empty esd")

    print(s)

    server.start()

    print("\n" + bold("DONE"))


if __name__ == "__main__":
    main()