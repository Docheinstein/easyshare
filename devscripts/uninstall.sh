#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
. "$SCRIPT_DIR/utils.sh"

echo_cyan "========= UNINSTALL ========"

pip uninstall easyshare
