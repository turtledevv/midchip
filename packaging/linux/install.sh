#!/usr/bin/env bash
# Installs MidChip system-wide.
#
# Expects to be run from an extracted release bundle, i.e. this script's
# directory contains: midchip, midchip-viz, midchip-gui, _internal/, README.md
# (that's exactly what `dist/midchip/` looks like after scripts/build.sh).
#
# Usage:
#   sudo ./install.sh                 # installs to /opt/midchip (default)
#   ./install.sh --user               # installs to ~/.local/share/midchip, no sudo needed
#   sudo ./install.sh --prefix /custom/path
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/midchip"
DESKTOP_DIR="/usr/share/applications"
USER_MODE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --user)
            USER_MODE=1
            INSTALL_DIR="$HOME/.local/share/midchip"
            DESKTOP_DIR="$HOME/.local/share/applications"
            shift
            ;;
        --prefix)
            INSTALL_DIR="$2"
            shift 2
            ;;
        *)
            echo "error: unknown argument '$1'" >&2
            exit 1
            ;;
    esac
done

if [ "$USER_MODE" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "error: installing to $INSTALL_DIR requires root -- rerun with sudo, or pass --user" >&2
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/midchip-gui" ] || [ ! -d "$SCRIPT_DIR/_internal" ]; then
    echo "error: expected midchip-gui and _internal/ next to this script." >&2
    echo "       run this from inside the extracted dist/midchip bundle." >&2
    exit 1
fi

echo "Installing MidChip to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/"* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/midchip" "$INSTALL_DIR/midchip-viz" "$INSTALL_DIR/midchip-gui"

# Symlink CLI tools onto PATH so `midchip` / `midchip-viz` work from a terminal.
if [ "$USER_MODE" -eq 1 ]; then
    BIN_DIR="$HOME/.local/bin"
else
    BIN_DIR="/usr/local/bin"
fi
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/midchip" "$BIN_DIR/midchip"
ln -sf "$INSTALL_DIR/midchip-viz" "$BIN_DIR/midchip-viz"

mkdir -p "$DESKTOP_DIR"
sed "s|/opt/midchip|$INSTALL_DIR|g" "$SCRIPT_DIR/midchip.desktop" > "$DESKTOP_DIR/midchip.desktop"

# Also drop the icon into the standard hicolor theme path. Some desktop
# environments/menu indexers are picky about Icon= being a bare name
# resolved via the theme rather than an absolute path.
if [ -f "$SCRIPT_DIR/midchip.png" ]; then
    if [ "$USER_MODE" -eq 1 ]; then
        ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
    else
        ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
    fi
    mkdir -p "$ICON_DIR"
    cp "$SCRIPT_DIR/midchip.png" "$ICON_DIR/midchip.png"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    if [ "$USER_MODE" -eq 1 ]; then
        gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
    else
        gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Done."
echo "  Binaries:     $INSTALL_DIR/{midchip,midchip-viz,midchip-gui}"
echo "  On your PATH: midchip, midchip-viz  ($BIN_DIR)"
echo "  App launcher: MidChip (search your app menu, or run midchip-gui directly)"
if [ "$USER_MODE" -eq 1 ]; then
    echo "  Note: make sure $BIN_DIR is on your PATH."
fi