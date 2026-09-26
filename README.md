# LingoFlow

A private, local translation tool for reading on macOS. Select text or capture a region of the
screen, and a translation window appears next to what you are reading. Translation runs in
[Ollama](https://ollama.com) on your Mac, and OCR, the dictionary and speech use built-in macOS
services, so nothing you read leaves the computer.

Current version: **0.4.1** · see [CHANGELOG](CHANGELOG.md)

## Features

- **Translate a selection:** `Option+D`. Text streams in as the model generates it; you can
  select and copy while it streams.
- **Translate a screenshot:** `Option+S`. Recognition uses Apple Vision for English, Chinese and
  mixed text, and you can correct the recognized text before it is translated.
- **Look up single words:** one selected word shows an offline card from the Oxford
  English–Chinese dictionary that ships with macOS.
  - Card contents: UK/US phonetics with pronunciation, parts of speech, numbered senses and
    subject labels, with science senses emphasised.
  - Inflections are resolved (inhibited → inhibit, ran → run).
  - Fallback: terms missing from it show the English definition and the model's translation.
- **Translate typed text:** from the menu bar, with an explicit edit mode.
- **Long text:** complete input with no truncation, translated in parts. You can stop, retry,
  or continue from the unfinished part.
- **Pronunciation:** read the source, the translation or a selection aloud with installed macOS
  voices, offline.
- **Interface in English or Chinese:** Settings → General → Interface.

### The reading window

- The translation takes most of the space. The source appears as a short excerpt you can expand.
- Buttons appear only when they apply: stop, retry or continue, back to end, copy and speak.
- A new window is **unpinned**: it closes when you click in, or switch to, another app.
- Click the pin to keep it above other windows while you read. Pinning never flashes or moves
  the window.
- Clicks inside LingoFlow do not close it: menus, the language list, dragging, resizing,
  About and Settings.
- The window opens at a standard height, grows for long text, and remembers the size you set.

## Requirements

- macOS 13 or later; validated on Apple Silicon (arm64)
- [Ollama](https://ollama.com) with a translation model. The default is
  `hf.co/mradermacher/MiLMMT-46-4B-v1.0-GGUF:Q4_K_M` (about 3 GB), but any installed model can
  be chosen in Settings.
- Permissions: Accessibility (reading the selection), Input Monitoring (global hotkeys) and
  Screen Recording (screenshots). LingoFlow walks you through them on first launch; restart it
  after granting permissions.
- For word lookup: the Oxford English–Chinese dictionary enabled in the Dictionary app
  (Dictionary → Settings). Without it, single words are translated by the model.

## Install and run

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/macos-py312.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
ollama pull hf.co/mradermacher/MiLMMT-46-4B-v1.0-GGUF:Q4_K_M
.venv/bin/lingoflow
```

To build the menu bar app (no Dock icon) and optionally a DMG:

```bash
scripts/build_macos_app.sh      # dist/LingoFlow.app, signed with a local identity if present
scripts/build_dmg.sh            # dist/LingoFlow.dmg
```

The bundle contains its own Python runtime. `LingoFlow.app/Contents/MacOS/LingoFlow
--self-check <dir>` runs native checks with temporary data: windows and pinning, native event
monitors, the dictionary and OCR. Signing and packaging details are in
[packaging/macos/README.md](packaging/macos/README.md).

## Settings, data and privacy

| What | Where |
| --- | --- |
| Settings | `~/Library/Application Support/LingoFlow/settings.json` (older files migrate automatically) |
| Window size | `window-state.json` in the same folder; pin state is never stored |
| Log | `~/Library/Logs/LingoFlow/lingoflow.log` |

- **Settings sections:** General (interface and translation languages, hotkeys, screenshot
  text, reading window), Speech (voices, rate) and Model & Advanced (Ollama host, model
  parameters, prompts, diagnostics).
- **Privacy:** selected text, recognized text and translations are **not logged**, and no
  history is kept. The log records window events (menus, pinning, why a window closed) and
  timing only. Temporary screenshots are deleted after recognition. Both can be changed under
  Model & Advanced → Privacy and Diagnostics, for troubleshooting only.

## About the default model

MiLMMT uses its [official completion format with greedy decoding](https://github.com/xiaomi-research/gemmax#-translation-prompt).

- **Source language:** LingoFlow identifies it on the Mac; a single Latin-letter word is
  treated as English.
- **Long text:** translated in parts of at most 2048 UTF-8 bytes. This application limit
  prevents omissions seen in repeated-text stress tests; it is not an official context limit.
- **Other models:** style presets and custom prompts apply only to other models.

Quality notes and the model comparison are in [docs/MILMMT_DEFAULT_2026-09-26.md](docs/MILMMT_DEFAULT_2026-09-26.md).

## Development

```bash
.venv/bin/python scripts/run_checks.py                                     # isolated app data
.venv/bin/python scripts/run_checks.py --qt-platform cocoa tests/ui tests/integration
.venv/bin/python -m ruff check src tests scripts
```

Tests run against temporary app data and never call a real model. The Cocoa run uses native
windows and the real macOS dictionary and Vision frameworks. It does not replace checks with
real apps, permissions after installation, multiple displays or sleep/wake; those are listed
in [manual_tests/README.md](manual_tests/README.md).

Further reading:
- [Architecture](docs/ARCHITECTURE.md)
- [0.3.0 window and UI acceptance](docs/VALIDATION_UI_0.3.0_2026-09-26.md)
- [Dictionary lookup](docs/DICTIONARY_LOOKUP_2026-09-27.md)
- [Implementation history](docs/IMPLEMENTATION_STATUS.md)

## License

MIT
