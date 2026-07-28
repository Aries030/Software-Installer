#!/usr/bin/env sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMMAND="cd '$APP_DIR' && sudo python3 main.py"
PAUSE="printf '%s\n' 'Press Enter to close...'; read _"

if command -v x-terminal-emulator >/dev/null 2>&1; then
    exec x-terminal-emulator -e sh -c "$COMMAND; $PAUSE"
fi

if command -v mate-terminal >/dev/null 2>&1; then
    exec mate-terminal -- sh -c "$COMMAND; $PAUSE"
fi

if command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal -- sh -c "$COMMAND; $PAUSE"
fi

if command -v konsole >/dev/null 2>&1; then
    exec konsole -e sh -c "$COMMAND; $PAUSE"
fi

printf '%s\n' "No supported terminal emulator was found."
printf '%s\n' "Open a terminal in this folder and run: sudo python3 main.py"
exit 1
