from typing import List, Optional, Callable

from easyshare.args import Kwarg, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, Pargs, \
    ArgsParser, STR_PARAM
from easyshare.help import CommandHelp, CommandOptionHelp


class Esd(CommandHelp, ArgsParser):
    @classmethod
    def name(cls):
        return "esd"

    @classmethod
    def short_description(cls):
        return "server of the easyshare application"

    @classmethod
    def synopsis(cls):
        return f"""\
esd [<u>OPTION</u>]... [<u>SHARING</u> [<u>SHARING_NAME</u>] [<u>SHARING_OPTION</u>]...]"""

    @classmethod
    def long_description(cls):
        return """\

"""

    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    CONFIG = ["-c", "--config"]

    NAME = ["-n", "--name"]
    ADDRESS = ["-a", "--address"]
    PORT = ["-p", "--port"]
    DISCOVER_PORT = ["-d", "--discover-port"]
    PASSWORD = ["-P", "--password"]

    SSL_CERT = ["--ssl-cert"]
    SSL_PRIVKEY = ["--ssl-privkey"]
    REXEC = ["-e", "--rexec"]

    VERBOSE = ["-v", "--verbose"]
    TRACE = ["-t", "--trace"]
    NO_COLOR = ["--no-color"]

    def kwargs_specs(self) -> Optional[List[Kwarg]]:
        return [
            (self.HELP, PRESENCE_PARAM),
            (self.VERSION, PRESENCE_PARAM),
            (self.CONFIG, PRESENCE_PARAM),
            (self.NAME, STR_PARAM),
            (self.ADDRESS, STR_PARAM),
            (self.PORT, INT_PARAM),
            (self.DISCOVER_PORT, INT_PARAM),
            (self.PASSWORD, STR_PARAM),
            (self.SSL_CERT, STR_PARAM),
            (self.SSL_PRIVKEY, STR_PARAM),
            (self.REXEC, PRESENCE_PARAM),
            (self.VERBOSE, INT_PARAM_OPT),
            (self.TRACE, INT_PARAM_OPT),
            (self.NO_COLOR, PRESENCE_PARAM),
        ]

    def continue_parsing_hook(self) -> Optional[Callable[[str, ArgType, int, Args, List[str]], bool]]:
        return lambda argname, argtype, idx, args, positionals: argtype != ArgType.PARG

    @classmethod
    def options(cls) -> List[CommandOptionHelp]:
        return [
            CommandOptionHelp(cls.HELP, "show this help"),
            CommandOptionHelp(cls.VERSION, "show the easyshare version"),
            CommandOptionHelp(cls.CONFIG, "load settings from a esd configuration file", params=["config_path"]),
            CommandOptionHelp(cls.NAME, "server name", params=["name"]),
            CommandOptionHelp(cls.ADDRESS, "server address (default is primary interface)", params=["address"]),
            CommandOptionHelp(cls.PORT, "server port (default is 12020)", params=["port"]),
            CommandOptionHelp(cls.DISCOVER_PORT, "port used to listen to discovery messages (default is 12021)", params=["port"]),
            CommandOptionHelp(cls.PASSWORD, "server password, plain or hashed with es-tools", params=["password"]),
            CommandOptionHelp(cls.SSL_CERT, "path to an SSL certificate", params=["cert_path"]),
            CommandOptionHelp(cls.SSL_PRIVKEY, "path to an SSL private key", params=["privkey_path"]),
            CommandOptionHelp(cls.REXEC, "enable rexec (remote execution)"),
            CommandOptionHelp(cls.VERBOSE, "set verbosity level", params=["level"]),
            CommandOptionHelp(cls.TRACE, "enable/disable tracing", params=["0_or_1"]),
            CommandOptionHelp(cls.NO_COLOR, "don't print ANSI escape characters")
        ]
