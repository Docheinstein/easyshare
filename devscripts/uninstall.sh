#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
. "$SCRIPT_DIR/utils.sh"

echo_cyan "========= UNINSTALL ========"

sudo pip uninstall easyshare
