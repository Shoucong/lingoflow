# LingoFlow Manual Release Checks

Run these checks from a signed `.app` installed through the `.dmg`.

## Fresh Install

- Quit any running LingoFlow instance.
- Open the latest `dist/LingoFlow.dmg`.
- Drag `LingoFlow.app` into `/Applications` and replace the previous copy.
- Launch `/Applications/LingoFlow.app`.
- Confirm the first-run permission window explains that permission changes require restart.
- Grant Accessibility, Input Monitoring, and Screen Recording if missing.
- Quit and reopen after permission changes.

## Core Workflow

- Select text in a normal app and press the translation hotkey.
- Confirm the popup appears without focusing the macOS menu bar.
- Confirm source and target language labels match Settings.
- Change target language in Settings, save, and run another translation.
- Confirm the popup uses the saved language without changing it inside the popup.

## OCR Workflow

- Trigger OCR from the tray and from the OCR hotkey.
- Select an area containing readable text.
- Confirm the popup remains visible until translation finishes.
- Confirm OCR screenshots are not retained by default under the app cache.

## Window Behavior

- Open Settings, then trigger translation and OCR.
- Confirm the popup can be closed while Settings remains open.
- Click outside the popup after translation completes.
- Confirm it closes and does not block reopening Settings from the tray.

## Packaging

- Run `scripts/check_macos_signing.sh dist/LingoFlow.app`.
- Run `scripts/build_dmg.sh`.
- Install from the new DMG over the old app.
- Confirm existing permissions are still trusted when bundle id and signing identity did not change.
