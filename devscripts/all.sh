#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"

. "$SCRIPT_DIR/utils.sh"

sudo "$SCRIPT_DIR/uninstall.sh"

"$SCRIPT_DIR/make-helps.sh"
"$SCRIPT_DIR/make-mans.sh"
"$SCRIPT_DIR/make-html.sh"
"$SCRIPT_DIR/build.sh"

sudo "$SCRIPT_DIR/install.sh"