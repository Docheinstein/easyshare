#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

if ! command_exists sphinx-build; then
  abort "sphinx must be installed for build docs"
fi

if ! pip_module_exists recommonmark; then
  abort "sphinx must be installed for build docs"
fi

echo_cyan "====== CREATING MANS ====="

# all
sphinx-build -M text docs/sphinx/src/mans/all docs/sphinx/build