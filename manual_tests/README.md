# LingoFlow Manual Release Checks

Run these checks from the signed 0.3.0 `.app` in `dist/ui-redesign-20260926/`
(installed at `/Applications/LingoFlow.app`). Evidence for 0.3.0 is recorded in
`docs/VALIDATION_UI_0.3.0_2026-09-26.md`; earlier releases in `docs/VALIDATION_2026-09-26.md`.
Items below are manual acceptance steps, not claims that they have already passed.
Launch the app normally: a direct binary launch from another process can report
Accessibility and Input Monitoring as missing even when the installed app has them.
Window events (no text content) are written to `~/Library/Logs/LingoFlow/lingoflow.log`
as `trace menu:`, `trace window:` and `trace popup:` lines for checking a session afterwards.

## Fresh Install

- Quit any running LingoFlow instance.
- Keep a copy of the current installed app for rollback.
- Copy `dist/ui-redesign-20260926/LingoFlow.app` (or a DMG built from it).
- Drag `LingoFlow.app` into `/Applications` and replace the previous copy.
- Launch `/Applications/LingoFlow.app`.
- Confirm the first-run permission window explains that permission changes require restart.
- Grant Accessibility, Input Monitoring, and Screen Recording if missing.
- Quit and reopen after permission changes.

## Core Workflow

- Select text in a normal app and press the translation hotkey.
- Confirm the popup appears without focusing the macOS menu bar.
- Confirm the header shows short Chinese language names; with 自动 the identified
  source language replaces 自动 once the model starts.
- Change 译文语言 in Settings, save, and run another translation.
- Repeat selection in Safari/your browser, a PDF reader and a text editor. Confirm
  the pre-existing clipboard survives the selection fallback. Try an app with no selection.
- Open 输入文字翻译… from the menu, enter text, and translate with ⌘↵ or 翻译.
  Clicking another app must not close the edit window; Esc with typed text asks first.
- After a translation, use ⋯ → 编辑原文, change the text and translate; 取消 restores the
  previous source and translation. After completion change the target language.
- Stop a long request, retain its partial output, and retry. Completed parts should
  replay once; edited source or changed model/language should start a fresh translation.

## OCR Workflow

- Trigger OCR from the tray and from the OCR hotkey.
- Select an area containing readable text.
- Confirm OCR first opens the edit mode with 翻译 / 取消; correct an OCR error and
  submit. Disabling 翻译前先校对识别结果 in Settings should restore direct translation.
- With a pinned reading window open, OCR keeps that window and shows the new text in it.
- Press Escape during screenshot selection; confirm normal use can resume.
- Confirm OCR screenshots are not retained by default under the app cache.

## Window Behavior

- A new window opens unpinned at a standard height near the pointer, even if the
  previous window was pinned or the app was restarted. Long text grows it, then scrolls.
- While a translation is streaming, select a word in the output and copy it with Cmd+C.
- Confirm incoming text is appended at the end and neither replaces nor extends the selection.
- Repeat with a backwards selection and with a selection that reaches the end of the output.
- Scroll up during streaming: the reading position stays and 回到末尾 appears; it disappears
  at the bottom. Finished translations show no Stop/Retry buttons and no character count.
- Translate source text containing literal tags such as `<b>word</b>` and an ampersand.
  Confirm the source is displayed and can be selected exactly as written.
- Unpinned: click another app or the desktop while waiting for the model, while streaming,
  after completion, after 停止 and after an error. Each closes the window and cancels work.
  ⌘Tab to another app also closes it; returning to LingoFlow's own About/Settings does not.
- Pinned: the pin icon is filled and highlighted; outside clicks and app switches keep the
  window above other apps without taking keyboard focus. Toggle 20 times: no flash, jump,
  scroll reset or lost selection (the log must not contain “hidden while open”).
- Unpin: the window stays until the next outside click.
- Open the target language list, ⋯ menu and right-click menus; drag and resize; copy and
  speak. None of these closes the window. A click outside that only closes an open menu
  leaves the window open.
- Close with the title-bar button or Escape; reopen: unpinned, previous size kept if you had
  resized it.
- Minimize during generation; new text must not reopen the window. Restore it to read the result.
- Move between monitors, unplug a display, and test a full-screen Space. The window must remain reachable.
- Check light/dark/system theme, opacity, font size, 原文与译文并排 and 显示原文.

## Interface Language

- A fresh install and older settings files show English. Switch Settings → General →
  Interface → Language to 中文 and save: the menu bar and an open reading window change
  immediately, keeping pin state, text and target language. Open About and Settings again
  to confirm they are Chinese; switch back to English.

## Menu Windows

- With the app in the background and in front, and with a pinned window open, click
  关于 LingoFlow once: it appears in front and is usable; reopening reuses it.
- 设置… and 权限与诊断… likewise open with one click; opening Settings leaves the reading
  window open. ⋯ → 朗读与音色设置… opens the 朗读 section.

## Pronunciation

- Select a source word and click the speaker next to the source; only the word should play.
  Without a selection, the whole source should play. Repeat with the speaker beside the
  translation after generation completes; while playing, the icon becomes a stop button.
- Test installed US/UK English and Chinese voices; verify source/target voices are independent.
- Rapidly start/stop/replace playback. Close the window and quit while speaking; audio must stop.
- Disconnect networking and repeat with already-installed voices. No automatic voice download is expected.

## Reliability

- Stop/restart Ollama, then retry. Use an invalid model tag and verify an explicit failure.
- Change settings while model enumeration is slow, then Save/Cancel/Escape; late results must be ignored.
- Sleep/wake the Mac and repeat translation/OCR. During a longer reading session, watch
  for increasing memory, duplicated hotkey triggers or growing background activity.

## Packaging

- Run `scripts/check_macos_signing.sh dist/ui-redesign-20260926/LingoFlow.app`.
- Run `LINGOFLOW_SKIP_APP_BUILD=1 LINGOFLOW_DIST_DIR="$PWD/dist/ui-redesign-20260926" scripts/build_dmg.sh`.
- Install from the new DMG over the old app.
- Confirm existing permissions are still trusted when bundle id and signing identity did not change.
- Optionally compare the same local model/text in Easydict after disabling its online services;
  the current repository comparison is source-based, not an installed-app timing test.
