#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
#PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$SCRIPT_DIR" || exit

MANS="../easyshare/res/helps/mans.json"
USAGES="../easyshare/res/helps/usages.json"

python make_helps.py man > "$MANS"
python make_helps.py usage > "$USAGES"