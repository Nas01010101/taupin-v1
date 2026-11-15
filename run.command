#!/bin/sh
# macOS (double-click): starts the local server and opens the browser. Needs Python 3.9+, nothing else.
cd "$(dirname "$0")" || exit 1
PYTHONPATH=src exec python3 -m taupin "$@"
