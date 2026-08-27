<p align="center">
  <img src="https://github.com/turtledevv/midchip/blob/main/assets/midchip-banner.png?raw=true" alt="MidChip banner">
</p>

<hr>

# 🎹 MidChip
Turn MIDI files into chiptune! *(wowies)*
<br><br>

## 🪛 How to use
Either:
- Grab the latest release from the [Releases](https://github.com/turtledevv/midchip/releases) tab (easiest, recommended)
- Pull the source and run it directly
- Build it yourself. (advanced, for nerds)
<br><br>

## 📜 Licensing
This project uses the GPL-3.0 license. Read [LICENSE](https://github.com/turtledevv/midchip/blob/main/LICENSE) for more info.<br>
<sub>*TL;DR: You can use, modify, and sell this program, but distributed derivatives must remain GPL-3.0 and provide the source code, etc..*</sub>
<br><br>

## ⌨️ Running from source

**Windows:**
`py -m midchip.gui`<br>
**Linux/macOS:**
`python3 -m midchip.gui`.
<br><br>

## 📺 Building

1. Get Python.
   Latest works for Linux/macOS; but for Windows you cannot use versions later than 3.13, due to PyGame. This may change in the future when they fix that.<br>
   Grab a release here: https://www.python.org/downloads/

2. Install requirements
   `cd` into the project root (if you don't have it on your computer already, download from GitHub or use `git clone`).<br>
   Then, run `pip install -r requirements.txt`.

3. Build it.<br>
  **Linux/macOS:** | Run `scripts/build.sh`.  
  **Windows:**     | Run `scripts\build.bat`.

Then, go to `dist/midchip/`, and you have your finished binaries.
However, from those; you can also build a platform *installer*.
<br><br>
| Platform | Command |
|---|---|
| Linux | `packaging/linux/build-appimage.sh`
| macOS | `packaging/macos/build-app.sh`
| Windows | `iscc packaging\windows\midchip.iss`

<sub>ℹ️ Windows installer command needs [Inno Setup 6](https://jrsoftware.org/isdl.php#v6) installed.</sub>
<br><br>

<hr>
<p align="center">
  Made with Python 🐍 · © 2026 Turtledevv 🐢
</p>
