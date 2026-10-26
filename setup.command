#!/bin/bash
# One-time setup for running AmbiEdge from source on macOS: creates .venv and installs dependencies.
# Double-click this file in Finder (the first time, right-click it and choose Open).
cd "$(dirname "$0")" || exit 1

fail() {
    echo
    echo "Setup failed. Install Python 3.9 or newer from https://www.python.org/downloads/macos/"
    echo "(the python.org installer includes the Tk library the window needs) and run this again."
    read -r -p "Press Return to close."
    exit 1
}

# Use the first Python whose Tk is new enough. Apple's own python3 ships Tk 8.5, which draws blank
# windows on current macOS, so python.org and Homebrew builds (python3.13 and so on) come first.
PY=
for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c "import sys, tkinter; sys.exit(sys.version_info < (3, 9) or tkinter.TkVersion < 8.6)" 2>/dev/null; then
        PY=$c
        break
    fi
done
if [ -z "$PY" ]; then
    echo "No Python 3.9+ with a working Tk 8.6 or newer was found."
    echo "With Homebrew, run: brew install python@3.13 python-tk@3.13"
    fail
fi
echo "Using $(command -v "$PY") ($("$PY" -V), Tk $("$PY" -c 'import tkinter; print(tkinter.TkVersion)'))"
"$PY" -m venv .venv || fail
.venv/bin/python -m pip install --upgrade pip || fail
.venv/bin/python -m pip install -r requirements.txt || fail
echo
echo "Done. Double-click start.command to run AmbiEdge."
read -r -p "Press Return to close."
