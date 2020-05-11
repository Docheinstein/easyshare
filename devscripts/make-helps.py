from typing import Type

import os
import datetime
import sys

# Add the the project directory to sys.path since this is outside
# the easyshare folder and the modules won't be seen otherwise
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)


from easyshare.es.commands import CommandInfo, COMMANDS_INFO


def generate_command_help_markdown(info: Type[CommandInfo]):
    options_strings = []
    for option in info.options():
        aliases, option_desc = option
        options_strings.append("    {}{}".format(", ".join(aliases).ljust(24), option_desc))

    options_strings = sorted(options_strings, key=lambda opt_str: opt_str[0][0])
    options_string = "\n".join(options_strings)

    s = f"""\
    <A> # alignment
<b>COMMAND</b>
    {info.name()} - {info.short_description()}

    {info.long_description()}

<b>SYNOPSIS</b>
    {info.name()}  {info.synopsis()}

<b>OPTIONS</b>
{options_string}"""

    return s


def generate_command_help_markdown_definition(info: Type[CommandInfo]):
    return "{} = \"\"\"\\\n{}\"\"\"".format(
        info.name().upper(), generate_command_help_markdown(info)
    )


if __name__ == "__main__":
    help_defs = [generate_command_help_markdown_definition(cmd_info)
                 for cmd_info in COMMANDS_INFO.values()]

    print("# Automatically generated {}".format(
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
        end="\n\n"
    )

    for help_def in help_defs:
        print(help_def, end="\n\n")
        print("# ============================================================", end="\n\n")
