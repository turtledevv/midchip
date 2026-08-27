# MidChip
Turn MIDI files into chiptune!


## How to use
1. Install dependencies | `pip install -r requirements.txt`
2. Run it.              | `python3 -m midchip`

You're welcome.

## Building

`scripts/build.sh` (Linux/macOS) or `scripts\build.bat` (Windows) produces
the shared onedir bundle at `dist/midchip/` (`midchip`, `midchip-viz`,
`midchip-gui`, `_internal/`); that's the **standalone** version, just
unzip and run.

From that bundle you can also build a platform **installer**:

| Platform | Command | Output |
|---|---|---|
| Linux | `packaging/linux/build-appimage.sh` | `dist/MidChip-x86_64.AppImage` — single-file **installer**, entirely self-contained (payload + install/uninstall logic baked into `AppRun`). Double-click for a minimal GUI (zenity) that asks user-vs-system install and shows a progress bar; run with `--user`/`--prefix DIR`/`--uninstall` from a terminal for the old headless behavior |
| macOS | `packaging/macos/build-app.sh [version]` | `dist/MidChip.app` |
| Windows | `iscc packaging\windows\midchip.iss` | `dist\midchip-windows-setup.exe` |

CI (`.github/workflows/build.yml`) builds both the standalone bundle and
the installer for all three platforms on every `v*` tag, or on demand via
workflow_dispatch.