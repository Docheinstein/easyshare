import os
import sys
import socket
from typing import List, Optional, Callable

from easyshare import logging
from easyshare.args import KwArgSpec, ParamsSpec, INT_PARAM, INT_PARAM_OPT, PRESENCE_PARAM, STR_PARAM
from easyshare.client.args import ArgsParser
from easyshare.conf import Conf, INT_VAL, STR_VAL, BOOL_VAL, ParseError
from easyshare.logging import get_logger
from easyshare.server.server import Server
from easyshare.server.sharing import Sharing
from easyshare.shared.args import Args
from easyshare.shared.common import APP_VERSION, APP_NAME_SERVER_SHORT, \
    APP_NAME_SERVER, DEFAULT_DISCOVER_PORT, SERVER_NAME_ALPHABET, ENV_EASYSHARE_VERBOSITY, easyshare_load_env
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.utils.colors import enable_colors
from easyshare.utils.net import is_valid_port
from easyshare.utils.ssl import create_server_ssl_context
from easyshare.utils.str import satisfy
from easyshare.utils.types import to_int, to_bool, is_valid_list

# ==================================================================

log = get_logger()


# === HELPS ===

HELP_APP = """easyshare deamon (esd)
...
"""


# === ARGUMENTS ===

class SharingArgs(ArgsParser):
    READ_ONLY = ["-r", "--read-only"]
    PASSWORD = ["-p", "--password"]


class EsdArgs(ArgsParser):
    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    VERBOSE =   ["-v", "--verbose"]
    TRACE =     ["-t", "--trace"]

    NO_COLOR =  ["--no-color"]

    CONFIG = ["-c", "--config"]
    NAME = ["-n", "--name"]

    # PORT = ["-p", "--port"]
    # WAIT =      ["-w", "--wait"]


    def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
        return [
            KwArgSpec(EsdArgs.HELP,
                      ParamsSpec(0, 0, lambda _: terminate("help"))),
            KwArgSpec(EsdArgs.VERSION,
                      ParamsSpec(0, 0, lambda _: terminate("version"))),
            # KwArgSpec(EsdArgs.PORT, INT_PARAM),
            # KwArgSpec(EsArgs.WAIT, INT_PARAM),
            KwArgSpec(EsdArgs.VERBOSE, INT_PARAM_OPT),
            KwArgSpec(EsdArgs.TRACE, INT_PARAM_OPT),
            KwArgSpec(EsdArgs.NO_COLOR, PRESENCE_PARAM),
            KwArgSpec(EsdArgs.CONFIG, STR_PARAM),
            KwArgSpec(EsdArgs.NAME, STR_PARAM),
        ]

    def _continue_parsing_hook(self) -> Optional[Callable[[str, int, 'Args', List[str]], bool]]:
        return lambda argname, idx, args, positionals: not positionals

class EsdConfKeys:
    G_NAME = "name"
    G_PASSWORD = "password"
    G_SSL = "ssl"
    G_SSL_CERT = "ssl_cert"
    G_SSL_PRIVKEY = "ssl_privkey"

    S_PATH = "path"
    S_READONLY = "readonly"

ESD_CONF_SPEC = {
    None: {
        # "port": INT_VAL,
        EsdConfKeys.G_NAME: STR_VAL,
        EsdConfKeys.G_PASSWORD: STR_VAL,
        EsdConfKeys.G_SSL: BOOL_VAL,
        EsdConfKeys.G_SSL_CERT: STR_VAL,
        EsdConfKeys.G_SSL_PRIVKEY: STR_VAL
    },
    "^\\[([a-zA-Z0-9_]+)\\]$": {
        EsdConfKeys.S_PATH: STR_VAL,
        EsdConfKeys.S_READONLY: BOOL_VAL,
    }
}


# ==================================================================


def main():
    easyshare_load_env()

    if len(sys.argv) <= 1:
        terminate(HELP_APP)

    # Parse arguments
    args = EsdArgs().parse(sys.argv[1:])

    if not args:
        abort("Error occurred while parsing arguments")

    # Verbosity
    if args.has_kwarg(EsdArgs.VERBOSE):
        log.set_verbosity(args.get_kwarg_param(EsdArgs.VERBOSE,
                                               default=logging.VERBOSITY_MAX))

    log.i("{} v. {}".format(APP_NAME_SERVER_SHORT, APP_VERSION))
    log.i("Starting with arguments\n%s", args)

    enable_colors(EsdArgs.NO_COLOR not in args)

    # Packet tracing
    if args.has_kwarg(EsdArgs.TRACE):
        enable_tracing(args.get_kwarg_param(EsdArgs.TRACE, 1))

    # Default values
    server_name = socket.gethostname()
    server_password = None
    server_ssl_enabled = False
    server_ssl_cert = None
    server_ssl_privkey = None

    # Config file

    if EsdArgs.CONFIG in args:
        cfg = None

        try:
            cfg = Conf.parse(
                path=args.get_kwarg_param(EsdArgs.CONFIG),
                sections_parsers=ESD_CONF_SPEC,
                comment_prefixes=["#", ";"]
            )
        except ParseError as err:
            abort("Parse of config file failed: {}".format(str(err)))

        if cfg:
            log.i("Config file parsed successfully:\n%s", cfg)

            # Config's global settings

            server_name = cfg.get_global_value(
                EsdConfKeys.G_NAME,
                default=server_name
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

            # if server_ssl_enabled:
            #     if not server_ssl_cert:
            #         log.w("ssl=true, but ssl_cert has not been specified")
            #
            #     if not server_ssl_privkey:
            #         log.w("ssl=true, but ssl_privkey has not been specified")

            # Config's sharings
            sharings = {}

            for s_name, s_settings in cfg.get_non_global_sections().items():
                s_path = s_settings.get(EsdConfKeys.S_PATH)
                s_readonly = s_settings.get(EsdConfKeys.S_PATH, False)

                if not s_path:
                    log.w("Invalid path for sharing '%s'; skipping it", s_name)
                    continue

                sharing = Sharing.create(
                    name=s_name,
                    path=s_path,
                    read_only=s_readonly
                )

                if not sharing:
                    log.w("Invalid or incomplete sharing config; skipping '%s'", s_name)
                    continue

                sharings[s_name] = sharing

    # Args from command line

    # Name
    server_name = args.get_kwarg_param(
        EsdArgs.NAME,
        default=server_name
    )

    # Validation

    if not satisfy(server_name, SERVER_NAME_ALPHABET):
        abort("Invalid server name: '{}'".format(server_name))

    # if not is_valid_port(port):
    #     abort("Invalid port")

    print("== LOCALS ==", locals())
    terminate("Enough for now...")

    # Add sharings from command line
    # If a sharing with the same name already exists due to config file,
    # the values of the command line will overwrite those

    sharings_noarg_params = args.get_params()

    # sharings_arg_mparams can contain more than one sharing params
    # e.g. [['home', '/home/stefano'], ['tmp', '/tmp']]
    sharings_arg_mparams = args.get_mparams(ServerArguments.SHARE)

    sharings_params = []

    # Eventually add sharing specified without -s (the first one)
    if sharings_noarg_params:
        sharings_params.append(sharings_noarg_params)

    # Eventually add sharings specified with -s or --sharing
    if sharings_arg_mparams:
        for sh_params in sharings_arg_mparams:
            sharings_params.append(sh_params)

    if sharings_params:
        # Add sharings to server
        for sharing_params in sharings_params:
            if not is_valid_list(sharing_params):
                log.w("Skipping invalid sharing")
                log.i("Invalid sharing params: %s", sharing_params)
                continue

            sharing = Sharing.create(
                path=sharing_params[0],
                name=sharing_params[1] if len(sharing_params) > 1 else None
                # auth=AuthFactory.parse(password)  # allow parameters...
            )

            if not sharing:
                log.w("Invalid or incomplete sharing config; skipping sharing '%s'", str(sharing))
                continue

            log.i("Adding valid sharing [%s]", sharing)

            sharings[sharing.name] = sharing

    # SSL

    ssl_context = None
    if ssl_enabled and ssl_cert and ssl_privkey:
        log.i("Creating SSL context")
        log.i("SSL cert path: %s", ssl_cert)
        log.i("SSL privkey path: %s", ssl_privkey)
        ssl_context = create_server_ssl_context(cert=ssl_cert, privkey=ssl_privkey)

    # Configure pyro server
    server = Server(discover_port=port, name=name, ssl_context=ssl_context)

    if not sharings:
        log.w("No sharings found, it will be an empty server")

    # Add every sharing to the server
    for sharing in sharings.values():
        print("+ " + sharing.name + " --> " + sharing.path)
        server.add_sharing(sharing)

    server.start()


if __name__ == "__main__":
    main()
