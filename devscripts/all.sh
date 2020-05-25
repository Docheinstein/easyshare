#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"

. "$SCRIPT_DIR/utils.sh"

"$SCRIPT_DIR/uninstall.sh"
"$SCRIPT_DIR/release.sh"
"$SCRIPT_DIR/install.sh"