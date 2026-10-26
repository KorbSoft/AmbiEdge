#!/bin/bash
# Builds AmbiEdge.app from this source checkout. Run setup.command once first.
# Double-click this file in Finder (the first time, right-click it and choose Open).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Python environment not found. Run setup.command first."
    read -r -p "Press Return to close."
    exit 1
fi
if ! scripts/build-macos-app.sh .venv/bin/python; then
    echo
    echo "Building the app failed. The messages above say why."
    read -r -p "Press Return to close."
    exit 1
fi
echo
echo "Done. Drag AmbiEdge from the Finder window that opens into Applications, then open it from there."
open -R dist/AmbiEdge.app
read -r -p "Press Return to close."
