@echo off
setlocal enabledelayedexpansion

rem note to self: windows is stupid, and so are batch files

cd /d "%~dp0.."

if not exist "entrypoints" (
    echo error: expected entrypoints\ and midchip\ in %cd% -- is this the project root? 1>&2
    exit /b 1
)
if not exist "midchip" (
    echo error: expected entrypoints\ and midchip\ in %cd% -- is this the project root? 1>&2
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller scripts\midchip.spec --noconfirm --distpath dist
if errorlevel 1 (
    echo error: build failed 1>&2
    exit /b 1
)

copy /y README.md dist\midchip\ >nul
if errorlevel 1 (
    echo error: failed to copy README.md 1>&2
    exit /b 1
)

if exist assets\midchip.png (
    copy /y assets\midchip.png dist\midchip\ >nul
)

echo Build complete: dist\midchip\
echo   dist\midchip\midchip.exe       (CLI)
echo   dist\midchip\midchip-viz.exe   (visualizer)
echo   dist\midchip\midchip-gui.exe   (GUI)
echo   dist\midchip\_internal\        (shared libs)
