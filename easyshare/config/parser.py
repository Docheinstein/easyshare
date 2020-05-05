import os
import re
from typing import Dict, Optional, List, Tuple

from easyshare.logging import get_logger
from easyshare.utils.types import is_list

log = get_logger()

class ConfParser:

    def __init__(self,
                 section_regex_filter="^\\[([a-zA-Z0-9_]+)\\]$",
                 comment_prefixes: List[str] = None):
        self._section_regex = re.compile(section_regex_filter)
        self._comment_prefixes = comment_prefixes if is_list(comment_prefixes) else ['#', ";"]
        self.data = {}

    def parse(self, path: str) -> Optional[Dict]:
        self.data = {}

        if not path or not os.path.isfile(path):
            log.e("Invalid config file path %s", path)
            return None

        cfg = open(path, "r")

        log.i("Parsing config file %s", path)

        current_section = None

        while True:
            # Read line
            line = cfg.readline()
            if not line:
                log.d("EOF")
                break

            line = line.strip()

            # Skip if it begins with the prefix
            if self._is_comment(line):
                continue

            log.i("%s", line)

            is_section, section_name = self._is_section(line)

            if is_section:
                current_section = section_name
                self.data[current_section] = {}
                continue

            key, _, val = line.partition("=")

            if key == line:
                # No = found
                log.i("Skipping line; no relevant content")
                continue

            # Found a line with <key>=<value>
            log.i("Found a key=val assignment")

            key = key.strip() # just in case
            val = val.strip() # just in case
            log.i("%s=%s", key, val)

            # Push the key val to the right section dictionary
            if current_section is None and None not in self.data:
                # Allocate the global section
                self.data[None] = {}

            # Push to the right section
            self.data[current_section][key] = val

        log.i("Parsing finished")

        cfg.close()

        return self.data


    def get_global_section(self) -> Optional[Dict]:
        return self.get_section(None)


    def get_section(self, section) -> Optional[Dict]:
        return self.data.get(section)

    def has_section(self, section) -> bool:
        return section in self.data

    def __contains__(self, item):
        return self.has_section(item)

    def _is_section(self, line) -> Tuple[bool, Optional[str]]:

        section_match = self._section_regex.match(line)

        if section_match:
            section_name = section_match.groups()[0]
            log.i("Found valid section name [%s]", section_name)
            return True, section_name

        return False, None

    def _is_comment(self, line) -> bool:
        for comment_prefix in self._comment_prefixes:
            if line.startswith(comment_prefix):
                return True
        return False