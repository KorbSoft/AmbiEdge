#!/bin/bash
# Builds dist/AmbiEdge.app (and dist/AmbiEdge-macOS.zip) with PyInstaller.
# Usage: scripts/build-macos-app.sh [python]   (default: .venv/bin/python, else python3)
# Used by build-app.command and the release workflow.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${1:-}
if [ -z "$PY" ]; then
    if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
fi

"$PY" -m pip install --quiet --upgrade pyinstaller pillow
"$PY" -m pip install --quiet -r requirements.txt
VERSION=$("$PY" -c "import ambiedge; print(ambiedge.__version__)")

mkdir -p build
"$PY" -m ambiedge.icon build/AmbiEdge.png
"$PY" -m PyInstaller --noconfirm --clean --windowed --name AmbiEdge \
    --icon build/AmbiEdge.png --osx-bundle-identifier com.korbsoft.ambiedge AmbiEdge.pyw

APP=dist/AmbiEdge.app
PLIST=$APP/Contents/Info.plist
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"
plutil -replace LSApplicationCategoryType -string "public.app-category.utilities" "$PLIST"
plutil -replace NSHumanReadableCopyright -string "GPL-3.0-or-later, KorbSoft" "$PLIST"

# Ad-hoc signature (no Apple developer account), applied after editing Info.plist so it's valid.
# macOS ties Screen Recording permission to it, so each new build needs the permission again.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

rm -f dist/AmbiEdge-macOS.zip
ditto -c -k --keepParent "$APP" dist/AmbiEdge-macOS.zip
echo "Built $APP ($VERSION)"
