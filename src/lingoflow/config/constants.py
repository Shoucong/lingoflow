"""
Application-wide constants.

All magic strings, default values, and configuration constants live here. 
"""

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# ===========================================================
# Application Metadata
# ===========================================================
APP_NAME = "LingoFlow"
try:
    APP_VERSION = version("lingoflow")
except PackageNotFoundError:
    APP_VERSION = "0.1.0"
APP_AUTHOR = "Shoucong Jiao"
BUNDLE_IDENTIFIER = "com.shoucong.lingoflow"

# ===========================================================
# Paths
# ===========================================================
# Native macOS app directories. Keep the legacy path only for one-time
# migration from earlier terminal-focused builds.
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
CONFIG_DIR = APP_SUPPORT_DIR
CONFIG_FILE = CONFIG_DIR / "settings.json"
CONFIG_BACKUP_FILE = CONFIG_DIR / "settings.backup.json"
LOG_DIR = Path.home() / "Library" / "Logs" / APP_NAME
LOG_FILE = LOG_DIR / "lingoflow.log"
CACHE_DIR = Path.home() / "Library" / "Caches" / APP_NAME
OCR_CAPTURE_DIR = CACHE_DIR / "OCR Captures"
SINGLE_INSTANCE_LOCK = APP_SUPPORT_DIR / f"{BUNDLE_IDENTIFIER}.lock"
SINGLE_INSTANCE_SOCKET = APP_SUPPORT_DIR / f"{BUNDLE_IDENTIFIER}.socket"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "lingoflow"
LEGACY_CONFIG_FILE = LEGACY_CONFIG_DIR / "settings.json"


def resource_path(*parts: str) -> Path:
    """Return a resource path in source checkout or PyInstaller bundle."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root).joinpath(*parts)
    return Path(__file__).resolve().parents[3].joinpath(*parts)


ASSETS_DIR = resource_path("assets")
APP_ICON_FILE = ASSETS_DIR / "LingoFlow.icns"

# ===========================================================
# Ollama Defaults
# ===========================================================
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "huihui_ai/hunyuan-mt-abliterated:7b-chimera"
GENERAL_MODEL = "gemma3:4b"
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

SUPPORTED_OCR_LANGUAGES = [
    "eng",
    "chi_sim",
    "chi_tra",
    "jpn",
    "kor",
    "fra",
    "deu",
    "spa",
    "por",
    "ita",
    "rus",
    "eng+chi_sim",
    "eng+jpn",
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
