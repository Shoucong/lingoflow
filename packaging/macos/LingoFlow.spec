# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LingoFlow.app."""

from pathlib import Path
import tomllib

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


APP_NAME = "LingoFlow"
BUNDLE_ID = "com.shoucong.lingoflow"

ROOT_DIR = Path(SPECPATH).resolve().parents[1]
APP_VERSION = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text())["project"]["version"]
ENTRYPOINT = ROOT_DIR / "packaging" / "macos" / "lingoflow_entry.py"
ENTITLEMENTS = ROOT_DIR / "packaging" / "macos" / "entitlements.plist"
ICON_PATH = ROOT_DIR / "assets" / "LingoFlow.icns"
ASSETS_DIR = ROOT_DIR / "assets"

hiddenimports = [
    "ApplicationServices",
    "AppKit",
    "Cocoa",
    "Foundation",
    "PyQt6.QtNetwork",
    "Quartz",
    "Vision",
    "objc",
]
hiddenimports += collect_submodules("lingoflow")

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT_DIR / "src")],
    binaries=[],
    datas=([(str(ASSETS_DIR), "assets")] if ASSETS_DIR.exists() else []) + copy_metadata("lingoflow"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "black",
        "click",
        "curio",
        "IPython",
        "ipykernel",
        "jedi",
        "jupyter_client",
        "jupyter_core",
        "matplotlib",
        "mypy",
        "nbformat",
        "numpy",
        "pandas",
        "parso",
        "prompt_toolkit",
        "psutil",
        "pygments",
        "pytest",
        "qtconsole",
        "rich",
        "ruff",
        "tornado",
        "traitlets",
        "trio",
        "zmq",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=str(ENTITLEMENTS),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundlePackageType": "APPL",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright (c) 2026 Shoucong Jiao",
    },
)
