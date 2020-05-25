#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."
DIST_DIR="$PROJECT_DIR/dist"

. "$SCRIPT_DIR/utils.sh"

last_version="$(find "$DIST_DIR" | sort | tail -n 1)"

echo_cyan "========= INSTALLING ========"

sudo pip install "$last_version"
