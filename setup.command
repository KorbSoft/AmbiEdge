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

# Prefer python.org's Python: Apple's own python3 ships an old Tk that can draw blank windows.
PY=/Library/Frameworks/Python.framework/Versions/Current/bin/python3
[ -x "$PY" ] || PY=python3
command -v "$PY" >/dev/null 2>&1 || fail
"$PY" -c "import tkinter" 2>/dev/null || {
    echo "This Python has no tkinter. With Homebrew, run: brew install python-tk"
    fail
}
"$PY" -c "import sys, tkinter; sys.exit(tkinter.TkVersion < 8.6)" || {
    echo "This Python uses Tk $("$PY" -c 'import tkinter; print(tkinter.TkVersion)'), which is too old for macOS."
    fail
}
"$PY" -m venv .venv || fail
.venv/bin/python -m pip install --upgrade pip || fail
.venv/bin/python -m pip install -r requirements.txt || fail
echo
echo "Done. Double-click start.command to run AmbiEdge."
read -r -p "Press Return to close."
