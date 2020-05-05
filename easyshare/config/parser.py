import os
import re
from typing import Dict, Optional, List, Tuple, Any, Callable, Union

from easyshare.logging import get_logger
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.types import to_int

log = get_logger()

class ParseError(Exception):
    pass

KeyValParser = Callable[[Union[str, None], str, str], Any] # section, key, val => Any

STR_PARSER = lambda sec, key, val: val
INT_PARSER = lambda sec, key, val: to_int(val, raise_exceptions=True)
BOOL_PARSER = lambda sec, key, val: True if val.lower() == "true" or val.lower() == "y" or val.lower() == "yes" else False


class Conf:

    def __init__(self, data: Dict):
        self.data = data


    def __str__(self):
        return json_to_pretty_str(self.data)


    @staticmethod
    def parse(path: str,
              sections_parsers: Dict[Union[str, None], Dict[str, KeyValParser]],
              comment_prefixes: List[str] = None) -> Optional['Conf']:

        comment_prefixes = comment_prefixes or []

        def is_comment(l: str) -> bool:
            for comment_prefix in comment_prefixes:
                if l.startswith(comment_prefix):
                    return True
            return False

        try:
            if not path or not os.path.isfile(path):
                log.e("Invalid config file path %s", path)
                raise ParseError("Invalid config path: '{}'".format(path))

            # Maps regex that specify the section name to the parses
            # of the key,val of that section
            sections_regex_parsers_map: Dict[re.Pattern, Dict[str, KeyValParser]] =\
                {re.compile(k) if k else None: v for k, v in sections_parsers.items()}
            data = {}

            cfg = open(path, "r")

            log.i("Parsing config file %s", path)

            current_section = None                       # global
            current_parsers = sections_parsers.get(None) # global

            while True:
                # Read line
                line = cfg.readline()
                if not line:
                    log.d("EOF")
                    break

                line = line.strip()

                log.i("%s", line)

                # Skip comment
                if is_comment(line):
                    continue

                # New section?
                for section_re, section_parsers in sections_regex_parsers_map.items():
                    if section_re:
                        section_match = section_re.match(line)

                        if section_match:
                            current_section = section_match.groups()[0]
                            current_parsers = section_parsers
                            log.i("Found known section pattern '%s'", current_section)
                            continue

                # Inside a section: check key=val pattern

                key, _, val = line.partition("=")

                if key == line:
                    if line:
                        log.w("Skipping unrecognized line: '%s'", line)
                    continue

                # Found a line with <key>=<value>
                log.d("Found a valid <key>=<val> assignment")

                key = key.strip()  # just in case
                val = val.strip()  # just in case
                log.d(" %s=%s", key, val)

                parser_found = False

                # Pass the key,val to the right parser
                for parser_key, parser_func in current_parsers.items():
                    if parser_key == key:
                        log.d("Passing '%s' to known parser", key)
                        parsed_val = parser_func(current_section, key, val)
                        if not current_section in data:
                            data[current_section] = {}

                        data[current_section][key] = parsed_val
                        parser_found = True
                        break

                if not parser_found:
                    log.w("No parser found for key '%s' inside section '%s'", key, current_section)


            log.i("Parsing finished")

            cfg.close()

            return Conf(data)
        except Exception as ex:
            raise ParseError(str(ex))


    def get_value(self, section: Union[str, None], key: str, default=None):
        sec = self.get_section(section)
        if not sec:
            return default
        return sec.get(key)

    def get_global_section(self) -> Optional[Dict]:
        return self.get_section(None)

    def get_section(self, section) -> Optional[Dict]:
        return self.data.get(section)

    def has_section(self, section) -> bool:
        return section in self.data

    def __contains__(self, item):
        return self.has_section(item)


if __name__ == "__main__":
    log.set_verbosity(5)
    try:

        cfg = Conf.parse(
            path="/home/stefano/Develop/Python/easyshare/res/esd.conf",
            sections_parsers={
                None: {
                    "port": INT_PARSER,
                    "name": STR_PARSER,
                    "ssl": STR_PARSER,
                    "ssl_cert": STR_PARSER,
                    "ssl_privkey": STR_PARSER
                },
                "^\\[([a-zA-Z0-9_]+)\\]$": {
                    "path": STR_PARSER,
                    "readonly": BOOL_PARSER,
                }
        }
        )
        print(cfg)
    except ParseError as ex:
        print("Parse failed with error: {}".format((str(ex))))
        raise ex