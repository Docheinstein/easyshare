import logging
import os
import re
from typing import Dict


class ServerConfigParser:

    COMMENT_PREFIX = "#"

    def __init__(self):
        self.sharing_name_re = re.compile("^\\[([a-zA-Z0-9_]+)\\]$")
        self.globals: Dict[str, str] = {}
        self.sharings: Dict[str, Dict[str, str]] = {}
        self.warnings = 0

    def __str__(self):
        s = ""

        # Globals
        for k, v in self.globals.items():
            s += "{}={}\n".format(k, v)

        s += "\n"

        # Sharings
        for sh, kv in self.sharings.items():
            s += "[{}]\n".format(sh)
            for k, v in kv.items():
                s += "  {}={}\n".format(k, v)
            s += "\n"

        return s

    def parse(self, config_path):
        if not config_path or not os.path.isfile(config_path):
            logging.warning("Invalid config file path %s", config_path)
            return False

        logging.info("Parsing config file %s", config_path)

        cfg = open(config_path, "r")

        current_sharing_section = None

        while True:
            line = cfg.readline()
            if not line:
                break

            if line.startswith(ServerConfigParser.COMMENT_PREFIX):
                continue

            line = line.strip()
            logging.debug("%s", line)

            sharing_name_match = self.sharing_name_re.match(line)

            if sharing_name_match:
                current_sharing_section = sharing_name_match.groups()[0]
                logging.trace("Found valid sharing name [%s]", current_sharing_section)
                self.sharings[current_sharing_section] = {}
                continue

            before, eq, after = line.partition("=")

            if before == line:
                # No = found
                logging.trace("Skipping line; no relevant content")
                self.warnings += 1
                continue

            logging.trace("Found a key=val assignment")

            key = before.strip()
            val = after.strip()
            logging.trace("%s=%s", key, val)

            if not current_sharing_section:
                # Found a key=val of a global setting
                self.globals[key] = val
            else:
                # Found a key=val of a sharing setting
                self.sharings[current_sharing_section][key] = val

        logging.info("Parsing finished")
        if self.warnings:
            logging.warning("%d warnings", self.warnings)

        cfg.close()

        return True

