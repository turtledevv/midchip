@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."

if not exist "entrypoints" (
    echo error: expected entrypoints\ and midchip\ in %cd% -- is this the project root? 1>&2
    exit /b 1
)
if not exist "midchip" (
    echo error: expected entrypoints\ and midchip\ in %cd% -- is this the project root? 1>&2
    exit /b 1
)

if exist midchip.spec del /q midchip.spec
if exist midchip-viz.spec del /q midchip-viz.spec
if exist midchip-gui.spec del /q midchip-gui.spec
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --name midchip --noconfirm --onefile --paths . --collect-all midchip ^
  --distpath dist\midchip-bundle entrypoints\cli.py
if errorlevel 1 (
    echo error: build failed for midchip 1>&2
    exit /b 1
)

pyinstaller --name midchip-viz --noconfirm --onefile --paths . --collect-all midchip ^
  --distpath dist\midchip-bundle entrypoints\viz.py
if errorlevel 1 (
    echo error: build failed for midchip-viz 1>&2
    exit /b 1
)

pyinstaller --name midchip-gui --noconfirm --onefile --windowed --paths . ^
  --collect-all midchip --collect-all tkinter ^
  --distpath dist\midchip-bundle entrypoints\gui.py
if errorlevel 1 (
    echo error: build failed for midchip-gui 1>&2
    exit /b 1
)

copy /y README.md dist\midchip-bundle\ >nul
if errorlevel 1 (
    echo error: failed to copy README.md 1>&2
    exit /b 1
)

echo Build complete: dist\midchip-bundle\