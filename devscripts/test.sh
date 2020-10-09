#!/bin/sh
# usage test-sh [test_file_name] [test_function_name]

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

if [[ -n "$1" ]]; then
  if [[ -n "$2" ]]; then
      tox -- -s "tests/$1" -k "$2"
  else
      tox -- -s "tests/$1"
  fi
else
  tox -- -s
fi