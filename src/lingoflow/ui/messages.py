"""Centralized user-facing UI messages."""

from __future__ import annotations

from lingoflow.config.constants import APP_NAME

HOTKEYS_UNAVAILABLE_TITLE = "Hotkeys unavailable"
HOTKEYS_PERMISSION_RESTART = (
    "Grant Accessibility and Input Monitoring permissions, then restart LingoFlow."
)

OLLAMA_NOT_RUNNING_TITLE = "Ollama not running"
OLLAMA_START_COMMAND = "Start Ollama with 'ollama serve'"
OLLAMA_START_COMMAND_FOR_TRANSLATION = "Start Ollama with 'ollama serve' for translations to work."
OLLAMA_OFFLINE_STATUS = "Ollama offline"
OLLAMA_CONNECT_TRANSLATION_ERROR = "Cannot connect to Ollama.\nMake sure it's running: ollama serve"

NO_TEXT_SELECTED_TITLE = "No text selected"
NO_TEXT_SELECTED_MESSAGE = "Select some text and try again."

OCR_ERROR_TITLE = "OCR Error"
OCR_FAILED_MESSAGE = "OCR failed."
NO_TEXT_FOUND_TITLE = "No text found"
NO_TEXT_FOUND_MESSAGE = "Could not extract text from the selected area."

MODEL_NOT_FOUND_TITLE = "Model not found"

ALREADY_RUNNING_MESSAGE = "Use the menu bar icon to translate, run OCR, or open settings."

SETTINGS_OPEN_DISMISS_POPUP_REASON = "Opening settings, closing any existing popup"
QUIT_CANCEL_TRANSLATION_REASON = "Quitting, cancelling active translation"
POPUP_CLOSED_CANCEL_TRANSLATION_REASON = "Popup closed, cancelling active translation"
TARGET_LANGUAGE_CHANGED_CANCEL_REASON = "Target language changed, cancelling current translation"


def already_running_title() -> str:
    """Return the duplicate-launch notification title."""
    return f"{APP_NAME} is already running"


def model_fallback_message(model: str) -> str:
    """Return a session fallback model notification message."""
    return f"Using '{model}' for this session."
