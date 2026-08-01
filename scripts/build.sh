#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."  # always run from the project root

if [ ! -d entrypoints ] || [ ! -d midchip ]; then
    echo "error: expected entrypoints/ and midchip/ in $(pwd) -- is this the project root?" >&2
    exit 1
fi

rm -f midchip.spec midchip-viz.spec midchip-gui.spec
rm -rf build dist

pyinstaller --name midchip --noconfirm --onefile --paths . --collect-all midchip \
  --distpath dist/midchip-bundle entrypoints/cli.py

pyinstaller --name midchip-viz --noconfirm --onefile --paths . --collect-all midchip \
  --distpath dist/midchip-bundle entrypoints/viz.py

pyinstaller --name midchip-gui --noconfirm --onefile --windowed --paths . \
  --collect-all midchip --collect-all tkinter \
  --distpath dist/midchip-bundle entrypoints/gui.py

cp README.md dist/midchip-bundle/

echo "Build complete: dist/midchip-bundle/"