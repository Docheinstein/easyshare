#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"

. "$SCRIPT_DIR/utils.sh"

cd "$SCRIPT_DIR" || exit

python make_hmd.py