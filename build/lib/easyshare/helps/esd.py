from typing import List, Optional, Callable

from easyshare.args import Option, ArgType, Args, PRESENCE_PARAM, INT_PARAM_OPT, INT_PARAM, \
    ArgsSpec, STR_PARAM
from easyshare.helps import CommandHelp, CommandOptionInfo


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
        return lambda argname, argtype, idx, args, positionals: argtype != ArgType.POSITIONAL

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
esd <A> # just for alignment
<b>esd</b> [<u>OPTION</u>]... [<u>SHARING</u> [<u>SHARING_NAME</u>] [<u>SHARING_OPTION</u>]...]</a>"""

    @classmethod
    def see_also(cls):
        return "SEE THE MAN PAGE FOR MORE INFO AND EXAMPLES"

    @classmethod
    def long_description(cls):
        return """\
Server of the easyshare network application.

Files and directories can be shared in one of the following manners:
   <A>
1. By providing the path of the file/directory to share in the command line as <u>SHARING</u> 
2. By creating a configuration file and specifying it with the option <b>-c</b> <u>config</u>
</A>

The option 1. should be preferred for an easy one-shot sharing of a file or directory, \
since doesn't need the creation a configuration file, but has the limit that \
only a file or folder can be shared.

If given, <u>SHARING</u> must be a valid path to a local file or directory.
<u>SHARING_NAME</u> is an optional name to assign to the sharing, as it will be seen \
by clients. If not given, the name of the file/directory is used instead.
Currently the only supported <u>SHARING_OPTION</u> is the read-only flag, which \
can be enabled with <b>-r</b>, and denies any write operation on a directory sharing.

The server can be configured either with a configuration file (2.) or by giving \
<b>esd</b> the options you need. The command line arguments have precedence over \
the corresponding setting of the configuration file (i.e. if you specify an option \
in both the configuration file and as an argument, the argument will be taken into account).

The configuration file is composed of two parts.
   <A>
1. Global section
2. Sharings sections
</A>

Each line of a section has the form <u><key></u>=<u><value></u>.
The available <u><key></u> of the global section are:
<I+4>
<b>address</b>
<b>discover_port</b>
<b>name</b>
<b>no_color</b>
<b>password</b>
<b>port</b>
<b>rexec</b>
<b>ssl</b>
<b>ssl_cert</b>
<b>ssl_privkey</b>
<b>trace</b>
<b>verbose</b>
</I>

The available <u><key></u> of the sharings sections are:
<I+4>
<b>path</b>
<b>readonly</b>
</I>

The first lines of the configuration file belongs to the global section by default.
Each sharing section begins with "[<u>SHARING_NAME</u>]".
If you omit the <u>SHARING_NAME</u>, the name of the shared file or directory will be \
used instead.

See the section <b>EXAMPLES</b> for an example of a configuration file.

You might consider using <b>es-tools</b> for some facilities, such as:
  <A>
- Create a default configuration file
- Create a secure hash of a password, useful for avoid to give a plain password \
to <b>esd</b>.</a>"""

    @classmethod
    def examples(cls):
        return """\
Usage example:
   <a>
1. Share a file</a>
<b>esd</b> <u>/tmp/file</u>
   <a>
2. Share a directory, assigning it a name</a>
<b>esd</b>  <u>/tmp/shared_directory</u> <u>shared</u>
   <a>
3. Share multiples directories, and other settings</a>
<b>esd</b> <b>-c</b> <u>/home/user/.easyshare/esd.conf</u>


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
<I+4>
path="/home/stefano/Downloads"
</i>
[shared]
<I+4>
path="/tmp/shared"
readonly=true
</i>
# Automatic sharing name
[]
<I+4>
path="/tmp/afile"</i>"""
