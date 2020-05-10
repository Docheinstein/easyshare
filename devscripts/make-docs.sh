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

echo_cyan "====== CREATING DOCS ====="

echo_cyan "========== MAN ==========="
# es
sphinx-build -M man docs/es docs/es/build

# esd
sphinx-build -M man docs/esd docs/esd/build


echo_cyan "========== HTML ==========="
#sphinx-build -M man docs/source docs/build