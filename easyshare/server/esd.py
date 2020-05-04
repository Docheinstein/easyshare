import os
import sys
import socket

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.server.server import Server
from easyshare.server.sharing import Sharing
from easyshare.shared.args import Args
from easyshare.shared.common import APP_VERSION, APP_NAME_SERVER_SHORT, \
    APP_NAME_SERVER, DEFAULT_DISCOVER_PORT, SERVER_NAME_ALPHABET, ENV_EASYSHARE_VERBOSITY
from easyshare.config.parser import parse_config
from easyshare.tracing import enable_tracing
from easyshare.utils.app import terminate, abort
from easyshare.utils.colors import enable_colors
from easyshare.utils.net import is_valid_port
from easyshare.utils.ssl import create_server_ssl_context
from easyshare.utils.str import satisfy
from easyshare.utils.types import to_int, to_bool, is_valid_list

# ==================================================================

log = get_logger()

APP_INFO = APP_NAME_SERVER + " (" + APP_NAME_SERVER_SHORT + ") v. " + APP_VERSION


# === HELPS ===

HELP_APP = """easyshare deamon (esd)
...
"""


# === ARGUMENTS ===


class ServerArguments:
    TRACE = ["-t", "--trace"]
    VERBOSE = ["-v", "--verbose"]
    SHARE = ["-s", "--share"]
    CONFIG = ["-c", "--config"]
    PORT = ["-p", "--port"]
    NAME = ["-n", "--name"]
    READ_ONLY = ["-r", "--read-only"]
    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]
    NO_COLOR = ["--no-color"]


class ServerConfigKeys:
    PORT = "port"
    NAME = "name"
    PASSWORD = "password"
    SHARING_PATH = "path"
    SHARING_READ_ONLY = "readonly"
    SSL = "ssl"
    SSL_CERT = "ssl_cert"
    SSL_PRIVKEY = "ssl_privkey"


# === ERRORS ===


class ErrorsStrings:
    INVALID_PORT = "Invalid port"
    INVALID_SERVER_NAME = "Invalid server name"


# ==================================================================

# === TRACING ===


# def require_connection(api: API) -> API:
#     def wrapped_api(server: 'Server', *vargs, **kwargs) -> Optional[Response]:
#         client = server._current_request_client()
#         if not client:
#             log.e("Connection is required for '%s'", api.__name__)
#             return create_error_response(ServerErrors.NOT_CONNECTED)
#         return api(*vargs, **kwargs)
#     setattr(wrapped_api, "__name__", api.__name__)
#     return wrapped_api

def main():
    starting_verbosity = os.environ.get(ENV_EASYSHARE_VERBOSITY)
    starting_verbosity = to_int(starting_verbosity,
                                raise_exceptions=False,
                                default=logging.VERBOSITY_NONE)
    log.set_verbosity(starting_verbosity)
    log.d("Starting with verbosity = %d", starting_verbosity)

    if len(sys.argv) <= 1:
        terminate(HELP_APP)

    args = Args(sys.argv[1:])

    enable_colors(ServerArguments.NO_COLOR not in args)

    if ServerArguments.HELP in args:
        terminate(HELP_APP)

    if ServerArguments.VERSION in args:
        terminate(APP_INFO)

    verbosity = 0
    tracing = 0

    # if ServerArguments.VERBOSE in args:
    #     verbosity = to_int(args.get_param(ServerArguments.VERBOSE, default=VERBOSITY_VERBOSE))
    #     if verbosity is None:
    #         abort("Invalid --verbose parameter value")
    #
    # if ServerArguments.TRACE in args:
    #     tracing = to_int(args.get_param(ServerArguments.TRACE, default=1))
    #     if tracing is None:
    #         abort("Invalid --trace parameter value")
    #
    # init_logging(verbosity)
    # enable_tracing(True if tracing else False)
    enable_tracing(True)

    log.i(APP_INFO)

    # Init stuff with default values
    sharings = {}
    port = DEFAULT_DISCOVER_PORT
    name = socket.gethostname()
    password = None
    ssl_enabled = False
    ssl_cert = None
    ssl_privkey = None

    # Eventually parse config file
    config_path = args.get_param(ServerArguments.CONFIG)

    if config_path:
        def strip_quotes(s: str) -> str:
            return s.strip('"\'') if s else s

        cfg = parse_config(config_path)
        if cfg:
            log.i("Parsed config file\n%s", str(cfg))

            # Globals
            global_section = cfg.pop(None)
            if global_section:
                if ServerConfigKeys.PORT in global_section:
                    port = to_int(global_section.get(ServerConfigKeys.PORT))

                if ServerConfigKeys.NAME in global_section:
                    name = strip_quotes(global_section.get(ServerConfigKeys.NAME, name))

                if ServerConfigKeys.PASSWORD in global_section:
                    password = strip_quotes(global_section.get(ServerConfigKeys.PASSWORD, name))

                    if password:
                        log.d("Global password found")

                if ServerConfigKeys.SSL in global_section:
                    # to_bool
                    ssl_enabled = to_bool(global_section.get(ServerConfigKeys.SSL, ssl_enabled))

                    if ssl_enabled:
                        log.i("SSL required on")
                        ssl_cert = strip_quotes(global_section.get(ServerConfigKeys.SSL_CERT, ssl_cert))
                        ssl_privkey = strip_quotes(global_section.get(ServerConfigKeys.SSL_PRIVKEY, ssl_privkey))

                        if not ssl_cert:
                            log.w("SSL required on, but ssl_cert has not been specified")

                        if not ssl_privkey:
                            log.w("SSL required on, but ssl_cert has not been specified")

            # Sharings
            for sharing_name, sharing_settings in cfg.items():

                sharing_password = strip_quotes(sharing_settings.get(ServerConfigKeys.PASSWORD))

                if sharing_password:
                    log.i("Sharing %s is protected by password", sharing_name)

                sharing = Sharing.create(
                    name=strip_quotes(sharing_name),
                    path=strip_quotes(sharing_settings.get(ServerConfigKeys.SHARING_PATH)),
                    read_only=to_bool(sharing_settings.get(ServerConfigKeys.SHARING_READ_ONLY, False))
                    # auth=AuthFactory.parse(sharing_password if sharing_password else password)
                )

                if not sharing:
                    log.w("Invalid or incomplete sharing config; skipping '%s'", str(sharing))
                    continue

                log.i("Adding valid sharing %s", sharing_name)

                sharings[sharing_name] = sharing
        else:
            log.w("Parsing error; ignoring config file")

    # Read arguments from command line (overwrite config)

    # Globals (port, name, ...)

    # Port
    if ServerArguments.PORT in args:
        port = to_int(args.get_param(ServerArguments.PORT))

    # Name
    if ServerArguments.NAME in args:
        name = args.get_param(ServerArguments.NAME)

    # Validation
    if not is_valid_port(port):
        abort(ErrorsStrings.INVALID_PORT)

    if not satisfy(name, SERVER_NAME_ALPHABET):
        log.e("Invalid server name %s", name)
        abort(ErrorsStrings.INVALID_SERVER_NAME)

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
