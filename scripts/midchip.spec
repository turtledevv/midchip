# -*- mode: python ; coding: utf-8 -*-
#
# builds midchip, midchip-viz, and midchip-gui as ONE shared bundle.
#
# run w/:  pyinstaller scripts/midchip.spec --distpath dist
#        ^^ RUN THAT COMMAND FROM PROJECT ROOT, DIPSHIT!! ^^

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).parent  # scripts/ -> project root


# windows' shitty .ico file; no-op for linux; and the icons on macOS is handled by Info.plist
_icon_path = project_root / "packaging" / "windows" / "midchip.ico"
APP_ICON = str(_icon_path) if _icon_path.exists() else None

# app icon PNG used by tk and visualizer
_assets_dir = project_root / "assets"
ASSET_DATAS = [(str(_assets_dir), "assets")] if _assets_dir.is_dir() else []

common_kwargs = dict(
    pathex=[str(project_root)],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    datas=ASSET_DATAS,
)

a_cli = Analysis(
    [str(project_root / "entrypoints" / "cli.py")],
    **common_kwargs,
)

a_viz = Analysis(
    [str(project_root / "entrypoints" / "viz.py")],
    **common_kwargs,
)

a_gui = Analysis(
    [str(project_root / "entrypoints" / "gui.py")],
    **common_kwargs,
)

# MERGE deduplicates shared dependencies across all three analyses.
# each tuple is (Analysis, script_basename, output_name).
MERGE(
    (a_cli, "cli", "midchip"),
    (a_viz, "viz", "midchip-viz"),
    (a_gui, "gui", "midchip-gui"),
)
# the comment above is funny because it sounds like I know what I'm talking about!

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)
pyz_viz = PYZ(a_viz.pure, a_viz.zipped_data, cipher=block_cipher)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli, a_cli.scripts, [],
    exclude_binaries=True,
    name="midchip",
    console=True,
    icon=APP_ICON,
)

exe_viz = EXE(
    pyz_viz, a_viz.scripts, [],
    exclude_binaries=True,
    name="midchip-viz",
    console=True,
    icon=APP_ICON,
)

exe_gui = EXE(
    pyz_gui, a_gui.scripts, [],
    exclude_binaries=True,
    name="midchip-gui",
    console=False,   # windowed, like --windowed
    icon=APP_ICON,
)

# bundle shit
coll = COLLECT(
    exe_cli, a_cli.binaries, a_cli.zipfiles, a_cli.datas,
    exe_viz, a_viz.binaries, a_viz.zipfiles, a_viz.datas,
    exe_gui, a_gui.binaries, a_gui.zipfiles, a_gui.datas,
    strip=False,
    upx=True,
    name="midchip",
)
