# SnapEdit 📸

SnapEdit is a lightweight, fast, and feature-rich screenshot capture and annotation tool designed for Windows. It runs quietly in the system tray and allows you to capture your screen, add beautiful annotations, and save or copy your work effortlessly.

## ✨ Features

- **Global Hotkeys**: Instantly capture the full screen or a specific region using global keyboard shortcuts (even when the app is in the background).
- **Region Capture**: Smooth, translucent overlay for precise rectangular selection with real-time dimension display.
- **Timed Region Capture**: Select a region, choose a 3, 5, or 10 second delay, then interact through the countdown overlay to open menus, tooltips, and dropdowns before capture. Press `Esc` during the countdown to cancel.
- **Rich Annotation Tools**:
  - 🖱️ **Select/Move**: Easily select, resize, and move any drawn shape or text.
  - ✂️ **Shapes**: Draw Rectangles, Ellipses, Lines, and Arrows.
  - 🎨 **Colors & Strokes**: Customizable stroke widths and colors, with an option to fill shapes.
  - 📝 **Text**: Add text annotations with a clean, semi-transparent background.
  - ① **Number Bubbles**: Add sequential numbered bubbles (1, 2, 3...) to create step-by-step guides effortlessly.
- **Modern UI**: Dark-themed, sleek interface using PyQt6.
- **Easy Export**: Save to PNG, JPG, BMP or automatically copy the annotated screenshot straight to your clipboard.
- **Gallery**: Reopen recent captures (up to five within a 64 MiB pixel-cache budget) or images from the configured save folder directly in the editor.
- **Windows Integration**: Optionally start SnapEdit when signing in and prevent duplicate app instances.

## 🚀 Installation & Setup

### Option 1: Using the Standalone Executable (Recommended)

1. Navigate to the `dist/` directory.
2. Simply double-click on `SnapEdit.exe`.
3. The app will launch and minimize to the system tray (look for the purple camera icon in your taskbar corner).
4. Right-click the tray icon to access **Settings** or to **Exit**.

### Option 2: Running from Source

If you prefer to run the application from the Python source code, follow these steps:

#### Prerequisites
- **Python 3.10+**
- Windows OS (Tested on Windows 11)

#### Setup Steps
1. Clone or download this repository.
2. Open a terminal/command prompt in the project folder.
3. (Optional but recommended) Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
4. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the application:
   ```bash
   python main.py
   ```

## ⌨️ Default Hotkeys

- **Capture Fullscreen**: `Alt+Shift+1`
- **Capture Region**: `Alt+Shift+2`
- **Timed Region Capture**: `Alt+Shift+3`

*Note: You can easily customize these hotkeys by right-clicking the system tray icon and selecting **Settings**.*

## 🛠️ Editor Shortcuts

While the editor window is open, you can use these shortcuts to speed up your workflow:

- `V`: Select tool
- `T`: Text tool
- `B`: Number Bubble tool
- `L`: Line tool
- `A`: Arrow tool
- `R`: Rectangle tool
- `E`: Ellipse tool
- `Ctrl + S`: Save Image
- `Ctrl + C`: Copy to Clipboard
- `Ctrl + G`: Open Gallery
- `Ctrl + Z`: Undo
- `Ctrl + Y`: Redo
- `Delete` or `Backspace`: Delete selected annotation
- `Ctrl + Scroll` or `Ctrl + +/-`: Zoom In/Out
- `Ctrl + 0`: Reset Zoom to Fit

## Display scaling and capture startup

SnapEdit follows each monitor's Windows **Settings → System → Display → Scale**
for controls, icons, labels, and new annotation defaults. For example, the
default 3 px stroke at 100% becomes 6 px at 200%. The editor's size controls show
the scaled values and remain editable. Existing annotations are not changed by
moving the editor between monitors; saved images retain their original pixels.

Capture overlays keep physical pixel coordinates (including negative monitor
origins), so Qt's automatic coordinate scaling is intentionally disabled. Fonts
and the first editor are prepared before capture hotkeys become active. Normal
region capture crops the frozen preview; timed capture grabs a fresh image only
after its countdown finishes.

Regression checks (synthetic images, no desktop capture or config writes):

```bash
python -m unittest discover -s tests -v
```

Closing an editor releases its image/scene and pending DPI work immediately;
completed property popups and dialogs are destroyed. Recent captures stay only
in RAM, capped at five images and 64 MiB of pixel data (about two 4K images).
An image larger than that budget can still be edited/exported at full resolution
but is not retained in recent history. Saved files are never removed by cache
eviction. This budget does not include the active image, UI, or clipboard.

## ⚙️ Building the Executable

To compile your own standalone `.exe` from source, ensure you have `pyinstaller` installed, then run:

```bash
python scripts/build_windows.py
```

## GitHub release build

Pushing a Git tag in the form `vX.Y.Z` (for example, `v1.0.0`) starts the
Windows build workflow. The generated `SnapEdit.exe` is attached to the GitHub
Release, and its Windows file/product version is set to `X.Y.Z.0` (for example,
`1.0.0.0`).

```bash
git tag v1.0.0
git push origin v1.0.0
```
The build uses a restricted DLL search path so third-party tools cannot inject
incompatible DLLs (for example, Poppler's ICU) into the package. It then launches
the actual executable twice with hidden test widgets: once with only Windows on
PATH, and once with the caller's PATH. No screenshot, hotkey, clipboard or user
configuration is touched. A failed smoke test fails the build command.

The executable is `dist/SnapEdit.exe`; smoke-test reports are in `build/`.
Keep `SnapEdit.spec` in Git. Do not regenerate it with a generic one-file command.

## 📄 License
Copyright (C) 2026. All rights reserved.
