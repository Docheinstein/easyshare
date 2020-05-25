from typing import Optional, List

from easyshare.args import ArgsSpec, PRESENCE_PARAM, STR_PARAM, Option
from easyshare.helps import CommandHelp, CommandOptionInfo


class EsTools(CommandHelp, ArgsSpec):
    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]

    GENERATE_PASSWORD = ["-p", "--hash-password"]
    GENERATE_ESD_CONF = ["-c", "--generate-config"]

    def options_spec(self) -> Optional[List[Option]]:
        return [
            (self.HELP, PRESENCE_PARAM),
            (self.VERSION, PRESENCE_PARAM),
            (self.GENERATE_PASSWORD, STR_PARAM),
            (self.GENERATE_ESD_CONF, PRESENCE_PARAM),
        ]


    @classmethod
    def options(cls) -> List[CommandOptionInfo]:
        return [
            CommandOptionInfo(cls.HELP, "show this help"),
            CommandOptionInfo(cls.VERSION, "show the easyshare version"),
            CommandOptionInfo(cls.GENERATE_PASSWORD, "generate an hash of the password", params=["password"]),
            CommandOptionInfo(cls.GENERATE_ESD_CONF, "generate default esd.conf file"),
        ]

    @classmethod
    def name(cls):
        return "es-tools"

    @classmethod
    def short_description(cls):
        return "tools for administrators of easyshare servers"

    @classmethod
    def synopsis(cls):
        return f"""\
es-tools <A> # just for alignment
<b>es-tools</b> [<u>OPTION</u>]..."""

    @classmethod
    def see_also(cls):
        return "SEE THE MAN PAGE FOR MORE INFO AND EXAMPLES"

    @classmethod
    def long_description(cls):
        return """\
Collection of tools for administrators of easyshare servers.

If neither <b>-c</b> nor <b>-p</b> is given, an interactive script is started and you will \
be asked what to do."""

    @classmethod
    def examples(cls):
        return """\
Usage example:
   <a>
1. Generate a default config file</a>
<b>es-tools</b> <b>-c</b> > /tmp/esd.conf
   <a>
2. Create a secure hash of a password</a>
<b>es-tools</b> <b>-p</b> <u>aSecurePassword</u>
   <a>
3. Start the interactive script</a>
<b>es-tools</b>
What do you want to do?
1. Generate an hash of a password (hash)
2. Generate the default server configuration file
3. Generate a self signed SSL certificate"""