c# LingoFlow

A lightweight, Ollama-powered translation app with OCR support.

## Features

- **Quick Translation**: Select text and press `Alt+D` to translate
- **OCR Translation**: Press `Alt+S` to capture screen region and translate
- **Streaming Output**: See translations as they generate
- **Local & Private**: All processing done locally via Ollama

## Requirements

- Python 3.10+
- Ollama with a language model installed
- Tesseract OCR

## Installation
```bash
conda create -n lingoflow python=3.10 -y
conda activate lingoflow
conda install -c conda-forge tesseract -y
pip install -e ".[dev]"
```

## Usage
```bash
lingoflow
```

## License

MIT