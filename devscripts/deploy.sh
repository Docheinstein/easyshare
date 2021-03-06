#!/bin/sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_DIR="$SCRIPT_DIR/.."

. "$SCRIPT_DIR/utils.sh"

cd "$PROJECT_DIR" || exit

echo_cyan "========= DEPLOYING ========"

LAST=$(find dist -name "*.tar.gz" | sort -V | tail -n 1)

if [ -z "$LAST" ]; then
  abort "DEPLOY FAILED"
fi

echo "Deploying $LAST"
python -m twine upload --repository-url https://upload.pypi.org/legacy/ "$LAST"