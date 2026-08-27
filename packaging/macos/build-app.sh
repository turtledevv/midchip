#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."  # project root

VERSION="${1:-2.3.0}"
DIST_DIR="dist/midchip"
APP_DIR="dist/MidChip.app"

if [ ! -f "$DIST_DIR/midchip-gui" ] || [ ! -d "$DIST_DIR/_internal" ]; then
    echo "error: $DIST_DIR not found or incomplete -- run scripts/build.sh first" >&2
    exit 1
fi

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# whole onedir bundle goes into Contents/MacOS/ as-is
cp -r "$DIST_DIR/"* "$APP_DIR/Contents/MacOS/"
chmod +x "$APP_DIR/Contents/MacOS/midchip" \
         "$APP_DIR/Contents/MacOS/midchip-viz" \
         "$APP_DIR/Contents/MacOS/midchip-gui"

cp packaging/macos/midchip-launcher "$APP_DIR/Contents/MacOS/midchip-launcher"
chmod +x "$APP_DIR/Contents/MacOS/midchip-launcher"

sed "s/__VERSION__/$VERSION/g" packaging/macos/Info.plist.in > "$APP_DIR/Contents/Info.plist"

if [ -f packaging/macos/midchip.icns ]; then
    cp packaging/macos/midchip.icns "$APP_DIR/Contents/Resources/midchip.icns"
else
    echo "note: packaging/macos/midchip.icns not found -- app will use a generic icon"
fi

echo "Built: $APP_DIR"
echo "Distribute by zipping it, or drop it in a .dmg / Applications symlink:"
echo "  ditto -c -k --sequesterRsrc --keepParent \"$APP_DIR\" dist/MidChip-macos.zip"