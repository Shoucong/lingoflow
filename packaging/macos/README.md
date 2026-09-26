# macOS Packaging

This folder contains the PyInstaller setup for building `LingoFlow.app`.

## Build

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/macos-py312.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
scripts/build_macos_app.sh
```

The app bundle is written to:

```bash
dist/LingoFlow.app
```

The validated target is CPython 3.12.12, macOS arm64, PyQt6 6.11.0 with Qt 6.11.1,
PyObjC 12.1 and PyInstaller 6.20.0. The lock also pins the editable-build dependency
`editables`; build isolation is disabled to use the exact locked backend.
QtCore's Mach-O deployment target is macOS 13.0, reflected in the app's plist.
Pinned dependencies and a clean rebuild provide a reproducible environment;
this is not a promise of byte-identical signed bundles across machines.

An isolated output or build interpreter can be selected without changing the installed app:

```sh
LINGOFLOW_PYTHON="$PWD/.venv/bin/python" \
LINGOFLOW_DIST_DIR="$PWD/dist/refactor-20260926" \
LINGOFLOW_WORK_DIR="$PWD/build/refactor-20260926" scripts/build_macos_app.sh
```

Run the packaged native UI, Vision and lifecycle checks with temporary app data:

```sh
dist/LingoFlow.app/Contents/MacOS/LingoFlow --self-check "$PWD/build/bundle-check"
```

This explicit mode uses synthetic text/images and does not register hotkeys,
read the clipboard, take a screen capture, play audio or change permissions.
It writes screenshots and JSON evidence. Vision's first call can initialize
system recognition models. The normal app always runs OCR in a background task.

## DMG

To build the app bundle and package it into a drag-to-Applications DMG:

```bash
scripts/build_dmg.sh
```

The disk image is written to:

```bash
dist/LingoFlow.dmg
```

For a faster packaging pass when `dist/LingoFlow.app` already exists:

```bash
LINGOFLOW_SKIP_APP_BUILD=1 scripts/build_dmg.sh
```

`LINGOFLOW_DIST_DIR` applies to both scripts, so an isolated build can be packaged with:

```sh
LINGOFLOW_SKIP_APP_BUILD=1 LINGOFLOW_DIST_DIR="$PWD/dist/refactor-20260926" scripts/build_dmg.sh
```

## Signing

For a stable local identity, the following optional command creates and trusts a
certificate in Keychain. Review it before running; building does not run it automatically:

```bash
scripts/setup_local_signing_identity.sh
```

After that, `scripts/build_macos_app.sh` will automatically use
`LingoFlow Local Development` when it is available.

If no local identity exists, the build script falls back to ad-hoc signing:

```bash
codesign --sign -
```

For Developer ID signing, provide an identity:

```bash
LINGOFLOW_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
  scripts/build_macos_app.sh
```

To inspect the bundle's signing state:

```bash
scripts/check_macos_signing.sh
```

To skip signing during local debugging:

```bash
LINGOFLOW_SKIP_CODESIGN=1 scripts/build_macos_app.sh
```

## Notes

- `LSUIElement` is set in the app bundle so LingoFlow runs as a menu bar app without a Dock icon.
- The packaged app uses native macOS user directories: settings in `~/Library/Application Support/LingoFlow` and logs in `~/Library/Logs/LingoFlow`.
- A Qt lock file prevents duplicate launches; a local socket asks the already-running instance to surface itself when available.
- macOS permissions attach to the launched application identity. Ad-hoc rebuilds
  can require granting permissions again; a signature verification alone does not test TCC persistence.
- Public distribution still needs Developer ID signing and notarization before sharing the DMG widely.
