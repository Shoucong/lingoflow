# macOS Packaging

This folder contains the PyInstaller setup for building `LingoFlow.app`.

## Build

```bash
python -m pip install -e ".[package]"
scripts/build_macos_app.sh
```

The app bundle is written to:

```bash
dist/LingoFlow.app
```

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

## Signing

For smoother local testing, create a stable local signing identity once:

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
- macOS permissions should attach to `LingoFlow.app`, not `python3.10`, once launched from the bundle.
- Public distribution still needs Developer ID signing and notarization before sharing the DMG widely.
