#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
#PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$SCRIPT_DIR" || exit

HELPS_FILE="../easyshare/res/helps.json"
HELPS_DUMP_FILE="/tmp/helps.txt"

python make-helps.py > "$HELPS_FILE" 2> "$HELPS_DUMP_FILE"