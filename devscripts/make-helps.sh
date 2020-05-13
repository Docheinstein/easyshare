#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
#PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$SCRIPT_DIR" || exit

HELPS_FILE="../easyshare/res/helps.json"

python make-helps.py | tee "$HELPS_FILE"