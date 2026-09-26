# LingoFlow Manual Release Checks

Run these checks from the signed 0.2.0 `.app` in `dist/refactor-20260926/`.
Automated evidence is recorded in `docs/VALIDATION_2026-09-26.md`. Items below are
manual acceptance steps, not claims that those checks have already passed.
The bundle preflight currently reports Accessibility and Input Monitoring missing.

## Fresh Install

- Quit any running LingoFlow instance.
- Keep a copy of the current installed app for rollback.
- Open `dist/refactor-20260926/LingoFlow.dmg` (or copy its sibling `.app` directly).
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
- Repeat selection in Safari/your browser, a PDF reader and a text editor. Confirm
  the pre-existing clipboard survives the selection fallback. Try an app with no selection.
- Open “Translate Typed Text…” from the menu, enter text, and translate with Cmd+Return.
- Edit the source and translate again; after completion change the target language.
- Stop a long request, retain its partial output, and retry. Completed parts should
  replay once; edited source or changed model/language should start a fresh translation.

## OCR Workflow

- Trigger OCR from the tray and from the OCR hotkey.
- Select an area containing readable text.
- Confirm OCR first opens editable source with “Translate”; correct an OCR error
  and submit. Disabling OCR review in Settings should restore direct translation.
- Press Escape during screenshot selection; confirm normal use can resume.
- Confirm OCR screenshots are not retained by default under the app cache.

## Window Behavior

- While a translation is streaming, select a word in the output and copy it with Cmd+C.
- Confirm incoming text is appended at the end and neither replaces nor extends the selection.
- Repeat with a backwards selection and with a selection that reaches the end of the output.
- Scroll up during streaming and confirm the reading position stays put. Clear the selection
  and scroll back to the bottom to resume following new output.
- Translate source text containing literal tags such as `<b>word</b>` and an ampersand.
  Confirm the source is displayed and can be selected exactly as written.
- Open Settings, then trigger translation and OCR.
- Confirm the popup can be closed while Settings remains open.
- Click outside the popup after translation completes.
- Confirm it closes and does not block reopening Settings from the tray.
- Drag the native title bar and resize all edges/corners. Close and reopen to verify saved size.
- Pin the window, click outside and verify it remains visible. Unpin and verify
  the “hide on focus loss” setting is respected. Open the target, copy and speech menus.
- Minimize during generation; new text must not reopen the window. Restore it to read the result.
- Move between monitors, unplug a display, and test a full-screen Space. The saved window must remain reachable.
- Check light/dark/system theme, opacity, font size, horizontal/vertical layout and source visibility.

## Pronunciation

- Select a source word and click Speak source; only the word should play. Without a selection,
  the whole source should play. Repeat for the translated text after generation completes.
- Test installed US/UK English and Chinese voices; verify source/target voices are independent.
- Rapidly start/stop/replace playback. Close the window and quit while speaking; audio must stop.
- Disconnect networking and repeat with already-installed voices. No automatic voice download is expected.

## Reliability

- Stop/restart Ollama, then retry. Use an invalid model tag and verify an explicit failure.
- Change settings while model enumeration is slow, then Save/Cancel/Escape; late results must be ignored.
- Sleep/wake the Mac and repeat translation/OCR. During a longer reading session, watch
  for increasing memory, duplicated hotkey triggers or growing background activity.

## Packaging

- Run `scripts/check_macos_signing.sh dist/refactor-20260926/LingoFlow.app`.
- Run `LINGOFLOW_SKIP_APP_BUILD=1 LINGOFLOW_DIST_DIR="$PWD/dist/refactor-20260926" scripts/build_dmg.sh`.
- Install from the new DMG over the old app.
- Confirm existing permissions are still trusted when bundle id and signing identity did not change.
- Optionally compare the same local model/text in Easydict after disabling its online services;
  the current repository comparison is source-based, not an installed-app timing test.
