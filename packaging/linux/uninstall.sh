#!/usr/bin/env bash
# Removes a MidChip install created by install.sh.
# Usage: sudo ./uninstall.sh  |  ./uninstall.sh --user
set -euo pipefail

INSTALL_DIR="/opt/midchip"
DESKTOP_DIR="/usr/share/applications"
BIN_DIR="/usr/local/bin"

if [ "${1:-}" = "--user" ]; then
    INSTALL_DIR="$HOME/.local/share/midchip"
    DESKTOP_DIR="$HOME/.local/share/applications"
    BIN_DIR="$HOME/.local/bin"
elif [ "$(id -u)" -ne 0 ]; then
    echo "error: removing $INSTALL_DIR requires root -- rerun with sudo, or pass --user" >&2
    exit 1
fi

rm -rf "$INSTALL_DIR"
rm -f "$DESKTOP_DIR/midchip.desktop"
rm -f "$BIN_DIR/midchip" "$BIN_DIR/midchip-viz"

if [ "${1:-}" = "--user" ]; then
    rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/midchip.png"
else
    rm -f "/usr/share/icons/hicolor/256x256/apps/midchip.png"
fi

echo "MidChip removed."