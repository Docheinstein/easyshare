import datetime
from typing import List, Tuple


def generate_help(name: str, short_description, long_description: str, synopsis: str,
                  options: List[Tuple[List[str], str]]):
    options_strings = []
    for option in options:
        aliases, option_desc = option
        options_strings.append("{}{}".format(", ".join(aliases).ljust(24), option_desc))
    options_string = "\n".join(options_strings)

    s = f"""\
    <A> # alignment
<b>COMMAND</b>
    {name} - {short_description}

    {long_description}

<b>SYNOPSIS</b>
    {name}  {synopsis}

<b>OPTIONS</b>
    {options_string}"""

    return s


def generate_help_definition(
        name: str, short_description, long_description: str, synopsis: str,
        options: List[Tuple[List[str], str]]):
    return "{} = \"\"\"\\\n{}\"\"\"".format(name.upper(), generate_help(
        name=name, short_description=short_description, long_description=long_description,
        synopsis=synopsis, options=options
    ))


if __name__ == "__main__":
    help_defs = [
        generate_help_definition(
            name="ls",
            short_description="list remote directory content",
            long_description="List content of the remote FILE or the current remote directory if no FILE is specified.",
            synopsis="rls [OPTION]... [FILE]",
            options=[
                (["-a", "--all"], "show hidden files too")
            ]
        ),
        generate_help_definition(
            name="rls",
            short_description="list remote directory content",
            long_description="List content of the remote FILE or the current remote directory if no FILE is specified.",
            synopsis="rls [OPTION]... [FILE]",
            options=[
                (["-a", "--all"], "show hidden files too")
            ]
        )
    ]

    print("# Automatically generated {}".format(
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
        end="\n\n"
    )

    for help_def in help_defs:
        print(help_def, end="\n\n")
        print("# ============================================================", end="\n\n")