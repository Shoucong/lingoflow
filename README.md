# LingoFlow

A lightweight macOS translation app powered by Ollama, Apple Vision OCR, and native global hotkeys.

## Features

- **Quick Translation**: Select text and press `Option+D` to translate
- **OCR Translation**: Press `Option+S` to capture screen region and translate
- **Streaming Output**: See translations as they generate
- **Local & Private**: All processing done locally via Ollama

## Requirements

- macOS
- Python 3.10+
- Ollama with a language model installed
- Accessibility, Input Monitoring, and Screen Recording permissions

## Installation
```bash
conda create -n lingoflow python=3.10 -y
conda activate lingoflow
pip install -e ".[dev]"
```

## Usage
```bash
lingoflow
```

## macOS App Bundle
```bash
python -m pip install -e ".[package]"
scripts/build_macos_app.sh
open dist/LingoFlow.app
```

The app bundle is configured as a menu bar app, so it should not show a Dock icon when launched from Finder.

Settings are stored in `~/Library/Application Support/LingoFlow/settings.json`.
Logs are written to `~/Library/Logs/LingoFlow/lingoflow.log`.

## License

MIT
