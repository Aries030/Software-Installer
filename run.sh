#!/usr/bin/env sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP_DIR"

if command -v python3 >/dev/null 2>&1; then
    exec python3 cli.py
fi

if command -v python >/dev/null 2>&1; then
    exec python cli.py
fi

printf '%s\n' 'Python 3 is required to run Kylin Disk Hider.' >&2
exit 1
