import os
import re
from typing import Dict, Optional, List, Any, Callable, Union

from easyshare.logging import get_logger
from easyshare.utils.json import j
from easyshare.utils.types import to_int

log = get_logger(__name__)

class ConfParseError(Exception):
    pass

KeyValParser = Callable[[Union[str, None], str, str], Any] # section, key, val => Any

STR_VAL = lambda sec, key, val: val.strip('"\'') if val else val
INT_VAL = lambda sec, key, val: to_int(val, raise_exceptions=True)
BOOL_VAL = lambda sec, key, val: True if val.lower() == "true" or val.lower() == "y" or val.lower() == "yes" else False


class Conf:

    def __init__(self, data: Dict):
        self.data = data

    def __str__(self):
        return j(self.data)


    @staticmethod
    def parse(path: str,
              sections_parsers: Dict[Union[str, None], Dict[str, KeyValParser]],
              comment_prefixes: List[str] = None) -> 'Conf':

        comment_prefixes = comment_prefixes or []

        def is_comment(l: str) -> bool:
            for comment_prefix in comment_prefixes:
                if l.startswith(comment_prefix):
                    return True
            return False

        try:
            if not path or not os.path.isfile(path):
                raise ConfParseError("Invalid config path: '{}'".format(path))

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

                log.i(">> %s", line)

                # Skip comment
                if is_comment(line):
                    continue

                # New section?
                new_section_found = False

                for section_re, section_parsers in sections_regex_parsers_map.items():
                    if section_re:
                        section_match = section_re.match(line)

                        if section_match:
                            current_section = section_match.groups()[0]
                            current_parsers = section_parsers
                            new_section_found = True
                            break

                if new_section_found:
                    log.i("New section: '%s'", current_section)
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
                log.d("%s=%s", key, val)

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
        except Exception as err:
            raise ConfParseError(str(err))


    def has_section(self, section: Union[str, None]) -> bool:
        return section in self.data

    def get_sections(self) -> Optional[Dict]:
        return self.data

    def get_section(self, section: Union[str, None]) -> Optional[Dict]:
        return self.data.get(section)

    def has_key(self, section: Union[str, None], key: str) -> bool:
        return self.get_value(section, key)

    def get_value(self, section: Union[str, None], key: str, default=None) -> Any:
        sec = self.get_section(section)

        if not sec:
            return default

        if key not in sec:
            return default

        return sec[key]


    def get_non_global_sections(self) -> Optional[Dict]:
        return {k:v for k, v in self.data.items() if k is not None}

    def get_global_section(self) -> Optional[Dict]:
        return self.get_section(None)

    def get_global_value(self, key: str, default=None) -> Any:
        return self.get_value(None, key, default)

    def has_global_key(self, key: str) -> bool:
        return self.has_key(None, key)


    def __contains__(self, item) -> bool:
        return self.has_section(item)


if __name__ == "__main__":
    log.set_verbosity(5)
    try:

        cfg = Conf.parse(
            path="/easyshare/res/esd.conf",
            sections_parsers={
                None: {
                    "port": INT_VAL,
                    "name": STR_VAL,
                    "ssl": STR_VAL,
                    "ssl_cert": STR_VAL,
                    "ssl_privkey": STR_VAL
                },
                "^\\[([a-zA-Z0-9_]+)\\]$": {
                    "path": STR_VAL,
                    "readonly": BOOL_VAL,
                }
            }
        )
        print(cfg)
    except ConfParseError as exc:
        print("Parse failed with error: {}".format((str(exc))))
        raise exc