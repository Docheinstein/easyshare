import socket
import sys
import threading
from typing import List, Optional, cast, Callable, Dict

from easyshare import logging
from easyshare.args import Option, PRESENCE_PARAM, ArgsParseError, ArgType, Args, StrParams, VarArgsSpec
from easyshare.auth import AuthFactory
from easyshare.common import APP_VERSION, APP_NAME_SERVER, SERVER_NAME_ALPHABET, easyshare_setup, APP_INFO, \
    DEFAULT_SERVER_PORT, DEFAULT_DISCOVER_PORT
from easyshare.conf import Conf, INT_VAL, STR_VAL, BOOL_VAL, ConfParseError
from easyshare.esd.common import Sharing
from easyshare.esd.daemons.api import ApiDaemon
from easyshare.esd.daemons.discover import DiscoverDaemon
from easyshare.helps.esd import Esd
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfoFull
from easyshare.res.helps import get_command_usage
from easyshare.ssl import get_ssl_context, set_ssl_context
from easyshare.styling import enable_colors, bold
from easyshare.tracing import set_tracing_level, TRACING_NONE, TRACING_TEXT
from easyshare.utils import terminate, abort
from easyshare.utils.env import are_colors_supported
from easyshare.utils.json import j
from easyshare.utils.net import is_valid_port, get_primary_ip
from easyshare.utils.ssl import create_server_ssl_context
from easyshare.utils.str import satisfychars, tf, keepchars

if __name__ == "__main__":
    # Call it now before get_logger for enable colors properly
    # and let logger be initialized with/without colors
    easyshare_setup()

log = get_logger(__name__)


# ==================================
# ==== ENTRY POINT OF ESD ==========
# ==================================

# SYNOPSIS
# esd [OPTION]... [SHARING [SHARING_NAME] [SHARING_OPTION]...]
#
# -a, --address  address                          server address (default is primary interface)
# -c, --config  config_path                       load settings from a server configuration file
# -d, --discover-port  port                       port used to listen to discovery messages;
#                                                 -1 disables discovery (default is 12021)
# -e, --rexec                                     enable rexec (remote execution)
# -h, --help                                      show this help
# -n, --name  name                                server name (default is server hostname)
# --no-color                                      don't print ANSI escape characters
# -P, --password  password                        server password, plain or hashed with es-tools
# -p, --port  port                                server port (default is 12020)
# -s, --sharing  sh_path [sh_name] [sh_options]   sharing to serve
# --ssl-cert  cert_path                           path to an SSL certificate
# --ssl-privkey  privkey_path                     path to an SSL private key
# -t, --trace  0_or_1                             enable/disable tracing
# -v, --verbose  level                            set verbosity level
# -V, --version                                   show the easyshare version



# === ARGUMENTS ===

class SharingArgs(VarArgsSpec):
    """ Command line arguments provided after the sharing path/name"""
    READ_ONLY = ["-r", "--read-only"]
    SHARING = ["-s", "--sharing"]


    # def positionals_spec(self) -> Optional[OptionParams]:
    #     # The no -s case should be StrParams(1, 1)
    #     # but for allow the -s case we should not restrict positionals
    #     # parameters (since the name/path of the sharing could be provided
    #     # by the -s option)
    #     # BTW we have to be careful after the parse, since the name/path
    #     # could either be in positionals or in -s params (or in none of these)
    #     return StrParams(0, 0)

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.READ_ONLY, PRESENCE_PARAM),
            (self.SHARING, StrParams(1, 1)),
                # not actually an option
                # it's a trick for allow a chain of -s
        ]

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, Args, List[str]], bool]]:
        # Usually there is no need to do this kind of check for arguments parsing
        # but in this way we can break the parsing if we found an unknown option
        # which enables tricks such as not parsing if a -s (esd option) is found,
        # therefore allows a chain of -s sharing -s sharing ...
        def continue_parsing_func(argname, argtype, idx, args, positionals):
            nonlocal self
            if argtype == ArgType.OPTION and argname in SharingArgs.SHARING:
                if SharingArgs.get_sharing_params(args):
                    log.d("Breaking -s chain, sharing params already found")
                    return False # break the chain
                log.d("Found the first -s, the next one will break the chain")

            return True

        return continue_parsing_func

    @staticmethod
    def get_sharing_params(args: Args) -> Optional[List[str]]:
        if not args:
            log.w("Can't provide sharings params, args not parsed yet?")
            return None # not parsed yet

        sharings_params = args.get_option_params(SharingArgs.SHARING) # -s params
        if sharings_params:
            log.d("Providing sharing params from -s option")
            return sharings_params

        sharings_params = args.get_positionals() # positionals, without -s
        if sharings_params:
            log.d("Providing sharing params from positionals")
            return sharings_params

        return None


class EsdConfKeys:
    """ Keys of the configuration file of esd (-c config)"""
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
    "^\\[([a-zA-Z0-9_]*)\\]$": {
        EsdConfKeys.S_PATH: STR_VAL,
        EsdConfKeys.S_READONLY: BOOL_VAL,
    }
}


# ==================================================================

def main():
    # Already called
    # easyshare_setup()

    if len(sys.argv) <= 1:
        _print_usage_and_quit()

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
    if g_args.has_option(Esd.VERBOSE):
        log.set_verbosity(g_args.get_option_param(Esd.VERBOSE,
                                                  default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_SERVER, APP_VERSION))
    log.i("Starting with arguments\n%s", g_args)

    # Help?
    if Esd.HELP in g_args:
        _print_usage_and_quit()

    # Version?
    if Esd.VERSION in g_args:
        terminate(APP_INFO)

    # Default values
    verbosity = logging.VERBOSITY_NONE
    tracing = TRACING_NONE
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

    # Stored as a dict so that consecutive declaration of
    # sharings with the same name will keep only the last one
    sharings: Dict[str, Sharing] = {}

    def add_sharing(path: str, name: str, readonly: bool):
        if not path:
            log.w("Invalid path for sharing '%s'; skipping it", name)
            return

        sh = Sharing.create(
            name=name,
            path=path,
            read_only=readonly
        )

        if not sh:
            log.w("Invalid or incomplete sharing config; skipping it")
            return

        # Use sh.name instead of name so that we will use the autogenerated one
        # if not provided by the user
        log.d("Adding sharing for name = %s", sh.name)
        sharings[sh.name] = sh

        log.d("Currently added sharings: \n%s", j([sh._info_internal() for sh in sharings.values()]))

    # Read config file

    if Esd.CONFIG in g_args:
        cfg = None

        try:
            cfg = Conf.parse(
                path=g_args.get_option_param(Esd.CONFIG),
                sections_parsers=ESD_CONF_SPEC,
                comment_prefixes=["#", ";"]
            )
        except ConfParseError as err:
            log.exception("Exception occurred while parsing conf")
            abort(f"Parse of config file failed: {err}")

        if cfg:
            _, global_section = cfg.global_section()

            log.i("Config file parsed successfully:\n%s", cfg)

            # Config's global settings

            server_name = global_section.get(
                EsdConfKeys.G_NAME,
                server_name
            )

            server_address = global_section.get(
                EsdConfKeys.G_ADDRESS,
                server_address
            )

            server_port = global_section.get(
                EsdConfKeys.G_PORT,
                server_port
            )

            server_discover_port = global_section.get(
                EsdConfKeys.G_DISCOVER_PORT,
                server_discover_port
            )

            server_password = global_section.get(
                EsdConfKeys.G_PASSWORD,
                server_password
            )

            server_ssl_cert = global_section.get(
                EsdConfKeys.G_SSL_CERT,
                server_ssl_cert
            )
            server_ssl_privkey = global_section.get(
                EsdConfKeys.G_SSL_PRIVKEY,
                server_ssl_privkey
            )

            server_ssl_enabled = global_section.get(
                EsdConfKeys.G_SSL,
                server_ssl_cert and server_ssl_privkey
            )

            server_rexec = global_section.get(
                EsdConfKeys.G_REXEC,
                server_rexec and server_rexec
            )

            no_colors = global_section.get(
                EsdConfKeys.G_NO_COLOR,
                no_colors
            )

            tracing = global_section.get(
                EsdConfKeys.G_TRACE,
                tracing
            )

            verbosity = global_section.get(
                EsdConfKeys.G_VERBOSE,
                verbosity
            )

            # Config's sharings

            for s_name, s_settings in cfg.non_global_sections():
                s_path = s_settings.get(EsdConfKeys.S_PATH)
                s_readonly = s_settings.get(EsdConfKeys.S_READONLY, False)

                add_sharing(path=s_path, name=s_name, readonly=s_readonly)

    # Args from command line: eventually overwrite config settings

    # Name
    server_name = g_args.get_option_param(
        Esd.NAME,
        default=server_name
    )

    # Server address
    server_address = g_args.get_option_param(
        Esd.ADDRESS,
        default=server_address
    )

    # Server port
    server_port = g_args.get_option_param(
        Esd.PORT,
        default=server_port
    )

    # Discover port
    server_discover_port = g_args.get_option_param(
        Esd.DISCOVER_PORT,
        default=server_discover_port
    )

    # Password
    server_password = g_args.get_option_param(
        Esd.PASSWORD,
        default=server_password
    )

    # SSL cert
    server_ssl_cert = g_args.get_option_param(
        Esd.SSL_CERT,
        default=server_ssl_cert
    )

    # SSL privkey
    server_ssl_privkey = g_args.get_option_param(
        Esd.SSL_PRIVKEY,
        default=server_ssl_privkey
    )

    # SSL enabled: obviously we need both cert and privkey
    # But for now set True if either one of the two is valid
    # will report errors at the end
    server_ssl_enabled = server_ssl_enabled or server_ssl_cert or server_ssl_privkey

    # Rexec
    if g_args.has_option(Esd.REXEC):
        server_rexec = True

    # Colors
    if g_args.has_option(Esd.NO_COLOR):
        no_colors = True

    # Packet tracing
    if g_args.has_option(Esd.TRACE):
        # The param of -t is optional:
        # if not specified the default is TEXT
        tracing = g_args.get_option_param(
            Esd.TRACE,
            default=TRACING_TEXT
        )

    # Verbosity
    if g_args.has_option(Esd.VERBOSE):
        # The param of -v is optional:
        # if not specified the default is DEBUG
        verbosity = g_args.get_option_param(
            Esd.VERBOSE,
            default=logging.VERBOSITY_MAX
        )

    # Logging/Tracing/UI setup
    log.d("Colors: %s", not no_colors)
    log.d("Tracing: %s", tracing)
    log.d("Verbosity: %s", verbosity)

    enable_colors(are_colors_supported() and not no_colors)

    set_tracing_level(tracing)

    # TODO: doesn't work with -c for some reason
    if verbosity:
        log.set_verbosity(verbosity)


    # Parse sharing arguments
    # This might come either from
    # 1. Positional arguments (no -s specified), only a sharing can be provided
    # 2. Params of a -s option (multiple sharings can be provided)

    s_unparsed = g_args.get_unparsed_args()

    while s_unparsed:
        log.d("Found %d unparsed args: considering those sharing args", len(s_unparsed))

        s_args = None

        try:
            s_args = SharingArgs().parse(s_unparsed)
        except ArgsParseError as err:
            log.exception("Exception occurred while parsing args")
            abort("Parse of sharing arguments failed: {}".format(str(err)))

        # We have to be careful since we could find the name/path either
        # in positionals or in the params of "-s"
        sharing_params = SharingArgs.get_sharing_params(s_args)

        if sharing_params:

            add_sharing(
                path=sharing_params[0],
                name=sharing_params[1] if len(sharing_params) >= 2 else None,
                readonly=s_args.get_option_param(SharingArgs.READ_ONLY)
            )

            s_unparsed = s_args.get_unparsed_args() # eventually other -s definitions
        else:
            # else - break the chain (discard eventual junk in unparsed args)
            log.w("No sharing params, discarding trailing junk: %s", s_args.get_unparsed_args())



    g_args.get_option_params(Esd.SHARING)

    # Validation

    # - server name
    server_name = keepchars(server_name, SERVER_NAME_ALPHABET)
    if not server_name:
        abort("Invalid server name")

    # - ports
    for p in [server_port, server_discover_port]:
        # -1 is a special value for disable discovery
        if p and not is_valid_port(p) and p != -1:
            abort("Invalid port number {}".format(p))

    # - is a useful server?
    if not sharings and not server_rexec:
        log.e("No sharings found, and rexec disabled; nothing to do")
        _print_usage_and_quit()

    if not sharings:
        log.w("No sharings found, it will be an empty esd")


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

    if not server_ssl_enabled or not ssl_context:
        log.w("Server will start in plaintext mode; please consider using SSL")

    set_ssl_context(ssl_context)

    # Auth
    auth = AuthFactory.parse(server_password)

    log.i("Required server name: %s", server_name)
    log.i("Required server address: %s", server_address)
    log.i("Required server port: %s", str(server_port))
    log.i("Required server discover port: %s", str(server_discover_port))
    log.i("Required auth: %s", auth.algo_type())


    # Compute real name/port/discover port
    server_name = server_name or socket.gethostname()
    server_address = server_address or get_primary_ip()
    server_port = server_port if server_port is not None else DEFAULT_SERVER_PORT
    server_discover_port = server_discover_port if server_discover_port is not None else DEFAULT_DISCOVER_PORT

    # INIT api daemon
    api_d = ApiDaemon(
        address=server_address,
        port=server_port,
        sharings=list(sharings.values()),
        name=server_name,
        auth=AuthFactory.parse(server_password),
        rexec=server_rexec
    )

    # build server info
    server_info_full: ServerInfoFull = cast(ServerInfoFull, api_d.server_info())

    server_info_full["ip"] = api_d.address()
    server_info_full["port"] = api_d.port()

    server_info_full["discoverable"] = True if is_valid_port(server_discover_port) else False
    if server_info_full["discoverable"]:
        server_info_full["discover_port"] = server_discover_port

    # INIT discover daemon

    discover_d = None
    if is_valid_port(server_discover_port):
        discover_d = DiscoverDaemon(port=server_discover_port, trace=True, server_info=server_info_full)

    log.i("ApiDaemon started at %s:%d", api_d.address(), api_d.port())

    if discover_d:
        log.i("DiscoverDaemon started at %s:%d", discover_d.address(), discover_d.port())

    if not sharings:
        sharings_str = "NONE"
    else:
        sharings_str = "\n".join([f"* {sh.name} --> {sh.path}{'  (readonly)' if sh.read_only else ''}"
                        for sh in sharings.values()])

    # PRINT info

    if not auth.algo_security():
        auth_str = "no"
    else:
        auth_str = f"yes ({auth.algo_type()})"

    print(f"""\
================================

{bold("SERVER INFO")}

Name:               {server_name}
Address:            {api_d.address()}
Server port:        {api_d.port()}
Discover port:      {discover_d.port() if discover_d else "disabled"}
Authentication:     {auth_str}
SSL:                {tf(get_ssl_context(), "enabled", "disabled")}
Remote execution:   {tf(server_rexec, "enabled", "disabled")}
Version:            {APP_VERSION}

================================

{bold("SHARINGS")}

{sharings_str}

================================

{bold("RUNNING...")}
""")

    # START daemons

    # - discover
    th_discover = None
    if discover_d:
        th_discover = threading.Thread(target=discover_d.run, daemon=True)

    # - api
    th_api = threading.Thread(target=api_d.run, daemon=True)

    try:
        if th_discover:
            log.i("Starting DISCOVER daemon")
            th_discover.start()
        else:
            # Might be disabled for public server (for which discover won't work anyway)
            log.w("NOT starting DISCOVER daemon")

        log.i("Starting API daemon")
        th_api.start()

        log.i("Ready to handle requests")

        if th_discover:
            th_discover.join()
        th_api.join()

    except KeyboardInterrupt:
        log.d("CTRL+C detected; quitting")
        # Formally not a clean quit of the threads, but who cares we are exiting...

    print("\n" + bold("DONE"))


def _print_usage_and_quit():
    """ Prints the esd usage and exit """
    esd_usage = get_command_usage(Esd.name())

    if not esd_usage:
        # Something went wrong with the dynamic loading of the usage
        abort(f"Can't provide usage of '{Esd.name()}'")

    terminate(esd_usage)


if __name__ == "__main__":
    main()