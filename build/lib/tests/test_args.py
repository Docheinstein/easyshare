from easyshare import logging
from easyshare.args import STR_PARAM, INT_PARAM, Args, ArgsParseError, VARIADIC_PARAMS
from easyshare.logging import init_logging

init_logging(default_verbosity=logging.VERBOSITY_MAX)

def test_parse_success():
    print("test_parse_success ----------")

    args = Args.parse(
        "-p 12020 -c /tmp something".split(" "),
        positionals_spec=STR_PARAM,
        options_spec=[
            (["-p", "--port"], INT_PARAM),
            (["-c", "--config"], STR_PARAM),
        ]
    )
    assert args.get_option_param(["-p", "--port"]) == 12020
    assert args.get_option_param(["-c", "--config"]) == "/tmp"
    assert args.get_positional() == "something"

def test_parse_fail():
    try:
        Args.parse(
            "-p -c /tmp something".split(" "),
            positionals_spec=STR_PARAM,
            options_spec=[
                (["-p", "--port"], INT_PARAM),
                (["-c", "--config"], STR_PARAM),
            ]
        )
        raise AssertionError()
    except ArgsParseError:
        pass


def test_variadic():
    args = Args.parse(
        "-a 1 2 3 4 -c /tmp something".split(" "),
        positionals_spec=STR_PARAM,
        options_spec=[
            (["-a", "--add"], VARIADIC_PARAMS),
            (["-c", "--config"], STR_PARAM),
        ]
    )

    assert args.get_option_params(["-a", "--add"]) ==["1", "2", "3", "4"]
    assert args.get_option_param(["-c", "--config"]) == "/tmp"