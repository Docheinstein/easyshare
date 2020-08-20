import os
import re
from typing import Dict, Optional, List, Any, Callable, Union, Tuple

from easyshare.logging import get_logger
from easyshare.utils.json import j
from easyshare.utils.types import to_int

log = get_logger(__name__)

class ConfParseError(Exception):
    pass

KeyValParser = Callable[[Union[str, None], str, str], Any] # section, key, val => parsed value
SectionContent = Dict[str, Any] # key => parsed value
Section = Tuple[Union[str, None], SectionContent] # str => section content

STR_VAL = lambda sec, key, val: val.strip('"\'') if val else val # strip quotes
INT_VAL = lambda sec, key, val: to_int(val, raise_exceptions=True)
BOOL_VAL = lambda sec, key, val: True if (val.lower() == "true" or
                                         val.lower() == "y" or
                                         val.lower() == "yes" or
                                         val.lower == "enable") else False


class Conf:
    """
    Represents a parsed configuration file.
    Provides the 'parse' method for create a new 'Conf'.
    """
    def __init__(self, parsed: List[Tuple[str, Dict[str, Any]]]):
        self.parsed = parsed

    def __str__(self):
        return j(self.parsed)


    @staticmethod
    def parse(path: str,
              sections_parsers: Dict[Union[str, None], Dict[str, KeyValParser]],
              comment_prefixes: List[str] = None) -> 'Conf':
        """
        Parses the given configuration file using specific sections parsers
        and prefixes for comments.
        Raises 'ConfParseError' if something goes wrong
        """

        comment_prefixes = comment_prefixes or [] # no comments?

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
            parsed = []

            cfg = open(path, "r")

            log.i("Parsing config file %s", path)

            current_keys_parsers = sections_parsers.get(None)

            # global
            current_section_name = None
            current_section = {}
            parsed.append((current_section_name, current_section))

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
                            current_section_name = section_match.groups()[0]
                            current_keys_parsers = section_parsers
                            new_section_found = True
                            break

                if new_section_found:
                    log.i("Adding new section: '%s'", current_section_name)
                    # Add the section to the parsed sections
                    current_section = {}
                    parsed.append((current_section_name, current_section))
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
                for parser_key, parser_func in current_keys_parsers.items():
                    if re.match(parser_key, key):
                        log.d("Passing '%s' to known parser", key)
                        parsed_val = parser_func(current_section_name, key, val)
                        current_section[key] = parsed_val
                        parser_found = True
                        break
                    else:
                        log.d(f"Handler '{parser_key}' cannot handle key '{key}'")

                if not parser_found:
                    log.w("No parser found for key '%s' inside section '%s'", key, current_section)


            log.i("Parsing finished")

            cfg.close()

            return Conf(parsed)
        except Exception as err:
            raise ConfParseError(str(err))

    def global_section(self) -> Optional[Section]:
        """ Returns the global section (the first one) """
        for section in self.parsed:
            name, _ = section
            if name is None:
                return section
        return None

    def non_global_sections(self) -> List[Section]:
        """ Returns all the non global sections """
        return [section for section in self.parsed if section[0] is not None]
