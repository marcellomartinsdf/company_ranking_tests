#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=".vendor${PYTHONPATH:+:$PYTHONPATH}"

exec /usr/bin/python3 webapp.py "$@"
