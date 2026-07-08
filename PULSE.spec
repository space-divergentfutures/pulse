# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-dir spec for PULSE (spec §11).
#
# Build with:
#   pip install pyinstaller
#   pyinstaller PULSE.spec
#
# Output: dist\PULSE\  (a directory — NOT a single .exe).
# One-dir avoids the constant antivirus / SmartScreen false-positives that
# single-file builds trigger for unsigned open-source apps.

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

# Collect all pywebview internals (WebView2 interop files, Edge hooks, etc.)
_wv = collect_all("webview")
datas    += _wv[0]
binaries += _wv[1]
hiddenimports += _wv[2]

# Pulse web UI assets (HTML / CSS / JS loaded at runtime by pywebview)
datas += [
    ("pulse/ui/web",  "pulse/ui/web"),
    ("pulse/data",    "pulse/data"),
]

# Known hidden imports not always caught by analysis
hiddenimports += [
    # pystray Windows backend
    "pystray._win32",
    # PyWin32 modules used by pulse/platform/windows.py
    "win32api",
    "win32con",
    "win32gui",
    "win32ts",
    "win32process",
    "win32security",
    "pywintypes",
    "winerror",
    # Config / sync
    "yaml",
    # pkg_resources (pywebview dependency)
    "pkg_resources",
    "pkg_resources.extern",
]

a = Analysis(
    ["pulse/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PULSE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX can trigger antivirus on Windows; leave off
    console=False,     # windowed — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/pulse.ico",   # uncomment once an .ico file is added to assets/
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PULSE",
)
