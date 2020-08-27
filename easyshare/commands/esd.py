from typing import List, Optional, Callable

from easyshare.args import Option, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, \
    ArgsSpec, STR_PARAM
from easyshare.commands import CommandHelp, CommandOptionInfo


class Esd(CommandHelp, ArgsSpec):
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

    SHARING = ["-s", "--sharing"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.HELP, PRESENCE_PARAM),
            (self.VERSION, PRESENCE_PARAM),
            (self.CONFIG, STR_PARAM),
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
        def continue_parsing_func(argname, argtype, idx, args, positionals):
            if argtype == ArgType.POSITIONAL:
                return False # begin of a sharing params
            if argtype == ArgType.OPTION and argname in Esd.SHARING:
                return False # begin of sharings params chain (multiple -s)
            return True

        return continue_parsing_func

    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.HELP, "show this help"),
            CommandOptionInfo(cls.VERSION, "show the easyshare version"),
            CommandOptionInfo(cls.CONFIG, "load settings from a server configuration file", params=["config_path"]),
            CommandOptionInfo(cls.NAME, "server name (default is server hostname)", params=["name"]),
            CommandOptionInfo(cls.ADDRESS, "server address (default is primary interface)", params=["address"]),
            CommandOptionInfo(cls.PORT, "server port (default is 12020)", params=["port"]),
            CommandOptionInfo(cls.DISCOVER_PORT, "port used to listen to discovery messages; 1 disables discovery (default is 12021)",
                              params=["port"]),
            CommandOptionInfo(cls.PASSWORD, "server password, plain or hashed with es-tools", params=["password"]),
            CommandOptionInfo(cls.SSL_CERT, "path to an SSL certificate", params=["cert_path"]),
            CommandOptionInfo(cls.SSL_PRIVKEY, "path to an SSL private key", params=["privkey_path"]),
            CommandOptionInfo(cls.REXEC, "enable rexec (remote execution)"),
            CommandOptionInfo(cls.SHARING, "sharing to serve", params=["sh_path", "[sh_name]", "[sh_options]"]),
            CommandOptionInfo(cls.VERBOSE, "set verbosity level", params=["level"]),
            CommandOptionInfo(cls.TRACE, "enable/disable tracing", params=["0_or_1"]),
            CommandOptionInfo(cls.NO_COLOR, "don't print ANSI escape characters")
        ]


    @classmethod
    def name(cls):
        return "esd"

    @classmethod
    def short_description(cls):
        return "server of the easyshare application"

    @classmethod
    def synopsis(cls):
        return f"""\
*esd* [**OPTION**]... [**SHARING** [**SHARING_NAME**] [**SHARING_OPTION**]...]"""

    @classmethod
    def see_also(cls):
        return "SEE THE MAN PAGE FOR MORE INFO AND EXAMPLES"

    @classmethod
    def long_description(cls):
        return """\
Server of the easyshare network application.

Files and directories can be shared in one of the following manners:
.A .
1. By providing the path of the file/directory to share in the command line as **SHARING** 
2. By creating a configuration file and specifying it with the option **-c** **config**
./A

The option 1. should be preferred for an easy one-shot sharing of a file or directory, \
since doesn't need the creation a configuration file, but has the limit that \
only a file or folder can be shared (unless the option -s is used before each \
sharing path (and eventually name or options).

If given, **SHARING** must be a valid path to a local file or directory.
**SHARING_NAME** is an optional name to assign to the sharing, as it will be seen \
by clients. If not given, the name of the file/directory is used instead.
Currently the only supported **SHARING_OPTION** is the read-only flag, which \
can be enabled with **-r**, and denies any write operation on a directory sharing.

The server can be configured either with a configuration file (2.) or by giving \
**esd** the options you need. The command line arguments have precedence over \
the corresponding setting of the configuration file (i.e. if you specify an option \
in both the configuration file and as an argument, the argument will be taken into account).

The configuration file is composed of two parts.
.A .
1. Global section
2. Sharings sections
./A

Each line of a section has the form **<key>**=**<value>**.
The available **<key>** of the global section are:
    **address**
    **discover_port**
    **name**
    **no_color**
    **password**
    **port**
    **rexec**
    **ssl**
    **ssl_cert**
    **ssl_privkey**
    **trace**
    **verbose**

The available **<key>** of the sharings sections are:
    **path**
    **readonly**

The first lines of the configuration file belongs to the global section by default.
Each sharing section begins with "[**SHARING_NAME**]".
If you omit the **SHARING_NAME**, the name of the shared file or directory will be \
used instead.

See the section **EXAMPLES** for an example of a configuration file.

You might consider using **es-tools** for some facilities, such as:
.A.
- Create a default configuration file
- Create a secure hash of a password, useful for avoid to give a plain password \
to **esd**."""

    @classmethod
    def examples(cls):
        return """\
Usage example:

.A .
1. Share a file
./A
    **esd** **/tmp/file**

.A .
2. Share a directory, assigning it a name
./A
    **esd** **/tmp/shared_directory** **shared**

.A .
3. Share multiples directories, one as read only
./A
    **esd** **-s** **/home/user** **-r** **-s** **/tmp** **temp**

.A .
3. Share multiples directories, with a configuration file
./A
    **esd** **-c** **/home/user/.easyshare/esd.conf**

Configuration file example (esd.conf):

# ===== SERVER SETTINGS =====

name=stefano-arch
password=aSecurePassword

port=12020
discover_port=12019

ssl=true
ssl_cert="/tmp/cert.pem"
ssl_privkey="/tmp/privkey.pem"
ssl_privkey="/tmp/privkey.pem"

rexec=false

verbose=4
trace=1

# ===== SHARINGS =====

[download]
    path="/home/stefano/Downloads"
[shared]
    path="/tmp/shared"
    readonly=true
# Automatic sharing name
[]
    path="/tmp/afile"\
"""


class EsdUsage(Esd):
    @classmethod
    def helpname(cls):
        return cls.name() + ".usage"

    @classmethod
    def long_description(cls):
        return f"""\
**esd** is the server of *easyshare*, a client-server command line application 
written in Python for transfer files between network hosts."""

    @classmethod
    def examples(cls):
        return ""