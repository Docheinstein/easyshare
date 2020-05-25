#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

echo_cyan "========= BUILDING ========"
python setup.py sdist bdist_wheel