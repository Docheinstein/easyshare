#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

if ! command_exists sphinx-build; then
  abort "shinphx must be installed for build docs"
fi

if ! pip_module_exists recommonmark; then
  abort "shinphx must be installed for build docs"
fi

echo_cyan "====== CREATING MANS ====="

# es
sphinx-build -M man docs/sphinx/es docs/sphinx/build

# esd
sphinx-build -M man docs/sphinx/esd docs/sphinx/build

# es-tools
sphinx-build -M man docs/sphinx/es-tools docs/sphinx/build