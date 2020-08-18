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
sphinx-build -M man docs/sphinx/src/mans/all docs/sphinx/build

# es
#sphinx-build -M man docs/sphinx/src/mans/es docs/sphinx/build

# esd
#sphinx-build -M man docs/sphinx/src/mans/esd docs/sphinx/build

# es-tools
#sphinx-build -M man docs/sphinx/src/mans/es-tools docs/sphinx/build