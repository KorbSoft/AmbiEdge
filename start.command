#!/bin/bash
# Starts AmbiEdge from a source checkout on macOS. Run setup.command once first.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Python environment not found. Run setup.command first."
    read -r -p "Press Return to close."
    exit 1
fi
# Detach, so closing this Terminal window doesn't quit AmbiEdge.
nohup .venv/bin/python AmbiEdge.pyw >/dev/null 2>&1 &
