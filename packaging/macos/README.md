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

## Signing

By default, the build script uses ad-hoc signing:

```bash
codesign --sign -
```

For Developer ID signing, provide an identity:

```bash
LINGOFLOW_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
  scripts/build_macos_app.sh
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
- Public distribution still needs Developer ID signing, notarization, and a DMG or ZIP container.
