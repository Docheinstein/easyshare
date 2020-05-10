#!/bin/sh
SCRIPT_DIR="$(dirname "$0")"

"$SCRIPT_DIR/make-docs.sh"
"$SCRIPT_DIR/build.sh"
"$SCRIPT_DIR/install.sh"