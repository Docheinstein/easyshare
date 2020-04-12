import os
import re
from typing import Dict, Optional

from easyshare.shared.log import w, i, d, t


def parse_config(config_path: str, *,
                 section_regex_filter="^\\[([a-zA-Z0-9_]+)\\]$",
                 comment_prefix='#') -> Optional[Dict]:

    if not config_path or not os.path.isfile(config_path):
        w("Invalid config file path %s", config_path)
        return None

    i("Parsing config file %s", config_path)

    section_re = re.compile(section_regex_filter)
    data = {}
    current_section = None

    cfg = open(config_path, "r")

    while True:
        # Read line
        line = cfg.readline()
        if not line:
            break

        # Skip if it begins with the prefix
        if line.startswith(comment_prefix):
            continue

        line = line.strip()
        d("%s", line)

        section_match = section_re.match(line)

        # New section?
        if section_match:
            current_section = section_match.groups()[0]
            t("Found valid section name [%s]", current_section)
            data[current_section] = {}
            continue

        before, eq, after = line.partition("=")

        if before == line:
            # No = found
            d("Skipping line; no relevant content")
            continue

        # Found a line with <key>=<value>
        d("Found a key=val assignment")

        key = before.strip()
        val = after.strip()
        t("%s=%s", key, val)

        # Push the key val to the right section dictionary
        if not current_section:
            # Push to the unbound section (the first)
            if None not in data:
                data[None] = {}
            data[None][key] = val
        else:
            # Push to the right section
            data[current_section][key] = val

    i("Parsing finished")

    cfg.close()

    return data

