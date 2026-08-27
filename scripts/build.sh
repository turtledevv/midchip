#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."  # always run from project root

if [ ! -d entrypoints ] || [ ! -d midchip ]; then
    echo "error: expected entrypoints/ and midchip/ in $(pwd); is this the project root?" >&2
    exit 1
fi

rm -rf build dist

# one auto-magical build instead of 3 seperate ones like a dumbass.
# see scripts/midchip.spec for why I did this.
pyinstaller scripts/midchip.spec --noconfirm --distpath dist

cp README.md dist/midchip/

# put in the amazingly awful icon
if [ -f assets/midchip.png ]; then
    cp assets/midchip.png dist/midchip/midchip.png
fi

echo "Build complete: dist/midchip/"
echo "  dist/midchip/midchip       (CLI)"
echo "  dist/midchip/midchip-viz   (visualizer)"
echo "  dist/midchip/midchip-gui   (GUI)"
echo "  dist/midchip/_internal/    (shared libs)"