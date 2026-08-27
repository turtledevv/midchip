#!/usr/bin/env bash
# Packages the shared onedir build (dist/midchip/) into a single-file
# MidChip-x86_64.AppImage *installer*.
#
# Unlike a typical AppImage, this isn't a portable copy of the app --
# AppRun itself IS the installer: the install/uninstall logic (what used
# to live in packaging/linux/install.sh + uninstall.sh) is baked directly
# into AppRun below, alongside the app payload in usr/bin/. One file, no
# companion scripts needed on the target machine.
#
# Double-clicked from a file manager (zenity + a display present, no
# args), AppRun shows a small GUI: pick "just me" or "all users", then a
# progress bar while it installs. Run from a terminal with flags, it
# stays fully scriptable/headless -- no GUI is shown.
#
# Usage: run after scripts/build.sh, from the project root:
#   ./packaging/linux/build-appimage.sh
# Then, on the target machine:
#   ./MidChip-x86_64.AppImage                 # double-click, or run with no args: GUI
#   ./MidChip-x86_64.AppImage --user          # headless, installs to ~/.local/share/midchip
#   ./MidChip-x86_64.AppImage --prefix DIR    # headless, installs to a custom prefix
#   ./MidChip-x86_64.AppImage --uninstall             # headless, removes a /opt/midchip install
#   ./MidChip-x86_64.AppImage --uninstall --user      # headless, removes a --user install
#
# Downloads appimagetool on first use (cached in packaging/linux/.tools/).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."  # project root

DIST_DIR="dist/midchip"
APPDIR="dist/AppDir"
TOOLS_DIR="packaging/linux/.tools"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"

if [ ! -f "$DIST_DIR/midchip-gui" ] || [ ! -d "$DIST_DIR/_internal" ]; then
    echo "error: $DIST_DIR not found or incomplete -- run scripts/build.sh first" >&2
    exit 1
fi

mkdir -p "$TOOLS_DIR"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Fetching appimagetool ..."
    curl -fsSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

# Payload: onedir bundle + the real desktop file (Exec=/opt/midchip/...,
# rewritten at install time by AppRun below, same as install.sh always did).
cp -r "$DIST_DIR/"* "$APPDIR/usr/bin/"
cp packaging/linux/midchip.desktop "$APPDIR/usr/bin/midchip.desktop"
chmod +x "$APPDIR/usr/bin/midchip" "$APPDIR/usr/bin/midchip-viz" "$APPDIR/usr/bin/midchip-gui"

if [ ! -f "$APPDIR/usr/bin/midchip.png" ]; then
    if [ -f assets/midchip.png ]; then
        cp assets/midchip.png "$APPDIR/usr/bin/midchip.png"
    else
        echo "error: no midchip.png icon found (checked $DIST_DIR and assets/)" >&2
        exit 1
    fi
fi

# AppRun: the AppImage's entry point, and the entire installer -- GUI
# and all. install.sh / uninstall.sh inlined and pointed at
# $HERE/usr/bin (the payload baked into this same AppImage) instead of a
# companion dist/ folder on disk.
cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

HERE="$(dirname "$(readlink -f "${0}")")"
PAYLOAD_DIR="$HERE/usr/bin"

INSTALL_DIR="/opt/midchip"
DESKTOP_DIR="/usr/share/applications"
BIN_DIR="/usr/local/bin"
USER_MODE=0
UNINSTALL=0
EXPLICIT_MODE=0   # any install-mode flag given -> headless, no GUI

while [ $# -gt 0 ]; do
    case "$1" in
        --user)
            USER_MODE=1
            EXPLICIT_MODE=1
            INSTALL_DIR="$HOME/.local/share/midchip"
            DESKTOP_DIR="$HOME/.local/share/applications"
            BIN_DIR="$HOME/.local/bin"
            shift
            ;;
        --prefix)
            INSTALL_DIR="$2"
            EXPLICIT_MODE=1
            shift 2
            ;;
        --uninstall)
            UNINSTALL=1
            EXPLICIT_MODE=1
            shift
            ;;
        *)
            echo "error: unknown argument '$1'" >&2
            exit 1
            ;;
    esac
done

# ---- the actual install, shared by both the GUI and headless paths ----
# Emits zenity-progress-format lines ("N" for percent, "# text" for the
# status label) on stdout so it can be piped straight into
# `zenity --progress`; those lines are just harmless output otherwise.
do_install() {
    local install_dir="$1" desktop_dir="$2" bin_dir="$3" payload_dir="$4" user_mode="$5"

    echo "5"; echo "# Creating install directory..."
    mkdir -p "$install_dir"

    echo "30"; echo "# Copying files..."
    cp -r "$payload_dir/"* "$install_dir/"
    chmod +x "$install_dir/midchip" "$install_dir/midchip-viz" "$install_dir/midchip-gui"

    echo "60"; echo "# Linking commands onto PATH..."
    mkdir -p "$bin_dir"
    ln -sf "$install_dir/midchip" "$bin_dir/midchip"
    ln -sf "$install_dir/midchip-viz" "$bin_dir/midchip-viz"

    echo "75"; echo "# Registering app launcher..."
    mkdir -p "$desktop_dir"
    sed "s|/opt/midchip|$install_dir|g" "$payload_dir/midchip.desktop" > "$desktop_dir/midchip.desktop"

    echo "85"; echo "# Installing icon..."
    if [ -f "$payload_dir/midchip.png" ]; then
        if [ "$user_mode" -eq 1 ]; then
            icon_dir="$HOME/.local/share/icons/hicolor/256x256/apps"
        else
            icon_dir="/usr/share/icons/hicolor/256x256/apps"
        fi
        mkdir -p "$icon_dir"
        cp "$payload_dir/midchip.png" "$icon_dir/midchip.png"
    fi

    echo "95"; echo "# Refreshing desktop caches..."
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        if [ "$user_mode" -eq 1 ]; then
            gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
        else
            gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
        fi
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
    fi
    # KDE Plasma indexes .desktop files into its own sycoca cache;
    # update-desktop-database (MIME associations) doesn't touch that, so
    # newly-installed launchers can silently not show up in the menu
    # until this runs (or the user logs out/in).
    if command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1 || true
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then
        kbuildsycoca5 >/dev/null 2>&1 || true
    fi

    echo "100"; echo "# Done."
}

print_summary() {
    local install_dir="$1" bin_dir="$2" user_mode="$3"
    echo "Done."
    echo "  Binaries:     $install_dir/{midchip,midchip-viz,midchip-gui}"
    echo "  On your PATH: midchip, midchip-viz  ($bin_dir)"
    echo "  App launcher: MidChip (search your app menu, or run midchip-gui directly)"
    if [ "$user_mode" -eq 1 ]; then
        echo "  Note: make sure $bin_dir is on your PATH."
    fi
}

do_uninstall() {
    local install_dir="$1" desktop_dir="$2" bin_dir="$3" user_mode="$4"
    rm -rf "$install_dir"
    rm -f "$desktop_dir/midchip.desktop"
    rm -f "$bin_dir/midchip" "$bin_dir/midchip-viz"
    if [ "$user_mode" -eq 1 ]; then
        rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/midchip.png"
    else
        rm -f "/usr/share/icons/hicolor/256x256/apps/midchip.png"
    fi
    echo "MidChip removed."
}

# ---- headless path: --user / --prefix / --uninstall given explicitly ----
if [ "$EXPLICIT_MODE" -eq 1 ]; then
    if [ "$UNINSTALL" -eq 1 ]; then
        if [ "$USER_MODE" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
            echo "error: removing $INSTALL_DIR requires root -- rerun with sudo, or pass --user" >&2
            exit 1
        fi
        do_uninstall "$INSTALL_DIR" "$DESKTOP_DIR" "$BIN_DIR" "$USER_MODE"
        exit 0
    fi
    if [ "$USER_MODE" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
        echo "error: installing to $INSTALL_DIR requires root -- rerun with sudo, or pass --user" >&2
        exit 1
    fi
    echo "Installing MidChip to $INSTALL_DIR ..."
    do_install "$INSTALL_DIR" "$DESKTOP_DIR" "$BIN_DIR" "$PAYLOAD_DIR" "$USER_MODE" | while read -r line; do
        [[ "$line" == \#* ]] && echo "${line#\# }"
    done
    print_summary "$INSTALL_DIR" "$BIN_DIR" "$USER_MODE"
    exit 0
fi

# ---- interactive path: no flags -- try a minimal GUI ----
if command -v zenity >/dev/null 2>&1 && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    CHOICE=$(zenity --list --radiolist \
        --title="MidChip Installer" \
        --text="Install MidChip for:" \
        --hide-header --width=420 --height=220 \
        --column="Pick" --column="Option" \
        TRUE  "Just me (no admin needed)" \
        FALSE "All users on this system (needs admin)") || exit 1

    case "$CHOICE" in
        "All users"*)
            USER_MODE=0
            INSTALL_DIR="/opt/midchip"
            DESKTOP_DIR="/usr/share/applications"
            BIN_DIR="/usr/local/bin"
            ;;
        *)
            USER_MODE=1
            INSTALL_DIR="$HOME/.local/share/midchip"
            DESKTOP_DIR="$HOME/.local/share/applications"
            BIN_DIR="$HOME/.local/bin"
            ;;
    esac

    if [ "$USER_MODE" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
        if command -v pkexec >/dev/null 2>&1; then
            # pkexec runs do_install as root, but $PAYLOAD_DIR lives inside
            # this AppImage's FUSE mount, owned by the invoking (non-root)
            # user -- root generally can't read it directly (no
            # allow_other), so pointing the root process straight at it
            # silently no-ops every copy/link/sed. Stream the payload over
            # as a tar archive on stdin instead: the non-root side (which
            # *can* read the mount) does the reading, root just unpacks
            # what it's handed.
            tar -C "$PAYLOAD_DIR" -cf - . | pkexec bash -c "
                set -e
                $(declare -f do_install)
                tmp=\$(mktemp -d)
                trap 'rm -rf \"\$tmp\"' EXIT
                tar -xf - -C \"\$tmp\"
                do_install '$INSTALL_DIR' '$DESKTOP_DIR' '$BIN_DIR' \"\$tmp\" 0
            " | zenity --progress --title="Installing MidChip" --text="Starting..." --percentage=0 --auto-close --no-cancel
        else
            zenity --error --title="MidChip Installer" \
                --text="Installing for all users needs admin rights, and pkexec isn't available.\n\nRe-run this AppImage from a terminal with sudo, or choose \"Just me\" instead."
            exit 1
        fi
    else
        do_install "$INSTALL_DIR" "$DESKTOP_DIR" "$BIN_DIR" "$PAYLOAD_DIR" "$USER_MODE" \
            | zenity --progress --title="Installing MidChip" --text="Starting..." --percentage=0 --auto-close --no-cancel
    fi

    zenity --info --title="MidChip Installer" \
        --text="MidChip installed to $INSTALL_DIR.\n\nLook for \"MidChip\" in your app menu, or run midchip-gui directly."
    exit 0
fi

# ---- no GUI toolkit / no display -- fall back to the old headless default ----
echo "note: no display or zenity found -- run with --user, --prefix DIR, or as root for a system install." >&2
if [ "$(id -u)" -ne 0 ]; then
    echo "error: installing to $INSTALL_DIR requires root -- rerun with sudo, or pass --user" >&2
    exit 1
fi
echo "Installing MidChip to $INSTALL_DIR ..."
do_install "$INSTALL_DIR" "$DESKTOP_DIR" "$BIN_DIR" "$PAYLOAD_DIR" "$USER_MODE" | while read -r line; do
    [[ "$line" == \#* ]] && echo "${line#\# }"
done
print_summary "$INSTALL_DIR" "$BIN_DIR" "$USER_MODE"
EOF
chmod +x "$APPDIR/AppRun"

# appimagetool requires its own top-level .desktop + icon to build a
# valid AppImage. This describes the installer itself (Exec=AppRun), and
# is separate from usr/bin/midchip.desktop, the app's own desktop entry
# that AppRun installs onto the target system.
sed -e "s|^Name=.*|Name=MidChip Installer|" \
    -e "s|^Comment=.*|Comment=Install MidChip to this system|" \
    -e "s|^Exec=.*|Exec=AppRun|" \
    -e "s|^Icon=.*|Icon=midchip|" \
    packaging/linux/midchip.desktop > "$APPDIR/midchip.desktop"
cp "$APPDIR/usr/bin/midchip.png" "$APPDIR/midchip.png"

echo "Building AppImage ..."
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "dist/MidChip-x86_64.AppImage"

echo "Built: dist/MidChip-x86_64.AppImage"
echo "  Double-click it (or run with no args) for the GUI installer."
echo "  Headless: chmod +x dist/MidChip-x86_64.AppImage && ./dist/MidChip-x86_64.AppImage [--user|--prefix DIR|--uninstall]"