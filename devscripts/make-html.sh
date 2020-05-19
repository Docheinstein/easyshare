#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."
PROJECT_DIR="$(realpath "$PROJECT_DIR")"

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

if ! command_exists sphinx-build; then
  abort "shinphx must be installed for build docs"
fi

if ! pip_module_exists recommonmark; then
  abort "shinphx must be installed for build docs"
fi

echo_cyan "====== COPYING STUFF FOR SPHINX ====="

set -x
cp README.MD docs/sphinx/src/html
cp LICENSE docs/sphinx/src/html/LICENSE.txt
cp -r img/ docs/sphinx/src/html/img
{ set +x; } 2>/dev/null

echo_cyan "====== CREATING HTML ====="

# html
sphinx-build -M html docs/sphinx/src/html docs/sphinx/build
