"""
Application-wide constants.

All magic strings, default values, and configuration constants live here. 
"""

from pathlib import Path

# ===========================================================
# Application Metadata
# ===========================================================
APP_NAME = "LingoFlow"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Shoucong Jiao"

# ===========================================================
# Paths
# ===========================================================
# User config directory
CONFIG_DIR = Path.home() / ".config" / "lingoflow"
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_DIR = CONFIG_DIR / "logs"
LOG_FILE = LOG_DIR / "lingoflow.log"

# ===========================================================
# Ollama Defaults
# ===========================================================
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "huihui_ai/hunyuan-mt-abliterated:7b-chimera"
OLLAMA_CHAT_ENDPOINT = "/api/chat"
OLLAMA_TAGS_ENDPOINT = "/api/tags"

# ===========================================================
# Translation Defaults
# ===========================================================
DEFAULT_SOURCE_LANG = "auto"
DEFAULT_TARGET_LANG = "Chinese(Simplified)"

SUPPORTED_LANGUAGES = [
    "auto",
    "English",
    "Chinese(Simplified)",
    "Chinese(Traditional)",
    "Japanese",
    "Spanish",
    "French",
    "German",
    "Russian",
    "Italian",
    "Korean",
    "Thai",
    "Vietnamese",
]

# ===========================================================
# Hotkey Defaults
# ===========================================================
DEFAULT_TRANSLATE_HOTKEY = "<alt>+d"
DEFAULT_OCR_HOTKEY = "<alt>+s"

# ===========================================================
# UI Defaults
# ===========================================================
POPUP_MIN_WIDTH = 300
POPUP_MAX_WIDTH = 500
POPUP_MIN_HEIGHT = 100
POPUP_MAX_HEIGHT = 400

# ===========================================================
# Timeouts (seconds)
# ===========================================================
OLLAMA_CONNECT_TIMEOUT = 5.0
OLLAMA_READ_TIMEOUT = 60.0