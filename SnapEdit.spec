# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(SPECPATH)))
from scripts.build_windows import clean_environment, verify_dll_origins

# Keep direct `pyinstaller SnapEdit.spec` builds isolated too. This changes
# only this build process, not the machine's PATH or installed DLLs.
build_env = clean_environment()
for key in ("PATH", "PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
    if key in build_env:
        os.environ[key] = build_env[key]
    else:
        os.environ.pop(key, None)

a = Analysis(
    ['bootstrap.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
verify_dll_origins(a.binaries)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SnapEdit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version='version.txt',
)
