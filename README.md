# LingoFlow

A lightweight macOS translation app powered by Ollama, Apple Vision OCR, and native global hotkeys.

## Features

- **Quick Translation**: Select text and press `Option+D` to translate
- **OCR Translation**: Press `Option+S` to capture screen region and translate
- **Streaming Output**: See translations as they generate
- **Reading Window**: Native dragging/resizing, pinning, saved geometry and adjustable bilingual layout
- **Long Text**: Complete source, budgeted segments, stop/retry and in-memory resume
- **Editable Input**: Review OCR, correct source text, or use “Translate Typed Text…” from the menu
- **Pronunciation**: Select a word or read the whole source/translation with installed macOS voices
- **Local by Default**: Ollama on localhost, Apple Vision and system speech; text/history logging is off by default

## Requirements

- macOS 13+ (the pinned Qt runtime minimum); validated on Apple Silicon
- Python 3.12 for development; the app bundle includes its runtime
- Ollama with a language model installed
- Accessibility, Input Monitoring, and Screen Recording permissions

## Installation
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/macos-py312.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
ollama pull hf.co/mradermacher/MiLMMT-46-4B-v1.0-GGUF:Q4_K_M
```

## Usage
```bash
.venv/bin/lingoflow
```

## macOS App Bundle
```bash
scripts/build_macos_app.sh
open dist/LingoFlow.app
```

The app bundle is configured as a menu bar app, so it should not show a Dock icon when launched from Finder.
The lock file targets CPython 3.12 on macOS arm64, including wheel hashes and
build/test tools. Other architectures need a separately validated lock.
See [packaging notes](packaging/macos/README.md) for signing and bundle self-checks.

To build a drag-to-Applications DMG:

```bash
scripts/build_dmg.sh
open dist/LingoFlow.dmg
```

Settings are stored in `~/Library/Application Support/LingoFlow/settings.json`.
Logs are written to `~/Library/Logs/LingoFlow/lingoflow.log`.
Window geometry is stored separately in `window-state.json` beside settings.
Existing settings migrate with defaults for the new fields.

The default translation model is **MiLMMT-46-4B-v1.0 Q4_K_M**. It uses the
[official completion format and greedy decoding](https://github.com/xiaomi-research/gemmax#-translation-prompt),
with local source-language detection for Auto-detect. Isolated Latin terms default to English;
choose Text Source explicitly for ambiguous short text. Chinese variant names are mapped to
the model's exact supported language names. Same-language input is returned unchanged.
Each long-text segment uses the official prompt independently. MiLMMT does not use chat-style
system prompts, academic presets or previous-segment instruction text; the UI disables those
controls while retaining custom prompts for other models. Cancellation and resume remain available.
Existing saved model choices are retained; selecting the MiLMMT tag enables its adapter automatically.

## Validation

```sh
.venv/bin/python scripts/run_checks.py
.venv/bin/python scripts/run_checks.py --qt-platform cocoa tests/ui
```

See [architecture](docs/ARCHITECTURE.md), [implementation status](docs/IMPLEMENTATION_STATUS.md)
and [manual acceptance](manual_tests/README.md). Native widget tests do not certify
external-app selection, permissions after installation, physical multi-screen behavior or sleep/wake.

## License

MIT
