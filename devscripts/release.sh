#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"

. "$SCRIPT_DIR/utils.sh"

"$SCRIPT_DIR/make-hmd.sh"
"$SCRIPT_DIR/make-mans.sh"
"$SCRIPT_DIR/build.sh"