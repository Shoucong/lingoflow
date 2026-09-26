"""Centralized user-facing UI messages (log-only reasons stay in English).

Messages are looked up when accessed (``messages.NO_TEXT_SELECTED_TITLE``), so they
always follow the interface language chosen in Settings.
"""

from __future__ import annotations

from lingoflow.config.constants import APP_NAME
from lingoflow.i18n import tr

_TEXT = {
    "HOTKEYS_UNAVAILABLE_TITLE": ("Hotkeys unavailable", "快捷键不可用"),
    "HOTKEYS_PERMISSION_RESTART": (
        "Allow Accessibility and Input Monitoring in System Settings, then restart LingoFlow.",
        "请在系统设置中允许“辅助功能”和“输入监控”，然后重新启动 LingoFlow。",
    ),
    "OLLAMA_NOT_RUNNING_TITLE": ("Ollama is not running", "Ollama 未运行"),
    "OLLAMA_START_COMMAND": (
        "Start Ollama first (ollama serve).",
        "请先启动 Ollama（ollama serve）。",
    ),
    "OLLAMA_START_COMMAND_FOR_TRANSLATION": (
        "Translation needs the local Ollama. Start it with: ollama serve",
        "翻译需要本机的 Ollama，请先启动（ollama serve）。",
    ),
    "OLLAMA_CONNECT_TRANSLATION_ERROR": (
        "Cannot connect to Ollama.\nMake sure it is running: ollama serve",
        "无法连接 Ollama。\n请确认它正在运行：ollama serve",
    ),
    "NO_TEXT_SELECTED_TITLE": ("No text selected", "没有选中文字"),
    "NO_TEXT_SELECTED_MESSAGE": (
        "Select the text to translate, then press the hotkey.",
        "请先选中要翻译的文字，再按快捷键。",
    ),
    "SELECTION_UNAVAILABLE_TITLE": ("Cannot read the selection", "无法读取选中文字"),
    "SELECTION_UNAVAILABLE_MESSAGE": (
        "Check the Accessibility permission.",
        "请检查“辅助功能”权限。",
    ),
    "OCR_ERROR_TITLE": ("Screenshot text recognition failed", "截图识别失败"),
    "OCR_FAILED_MESSAGE": ("Screenshot text recognition failed.", "截图识别失败。"),
    "NO_TEXT_FOUND_TITLE": ("No text found", "没有识别到文字"),
    "NO_TEXT_FOUND_MESSAGE": (
        "The selected area has no readable text.",
        "所选区域中没有可识别的文字。",
    ),
    "MODEL_NOT_FOUND_TITLE": ("Translation model not found", "找不到翻译模型"),
    "MODEL_NOT_FOUND_MESSAGE": (
        "Choose an installed model in Settings → Model & Advanced, "
        "or install the configured model in Ollama.",
        "请在“设置 → 模型与高级”中选择已安装的模型，或在 Ollama 中安装当前模型。",
    ),
    "ALREADY_RUNNING_MESSAGE": (
        "Use the menu bar icon to translate, capture text or open Settings.",
        "请使用菜单栏图标翻译、截图识别或打开设置。",
    ),
}

# Internal status key and log-only reasons; not shown as translated text.
OLLAMA_OFFLINE_STATUS = "Ollama offline"
QUIT_CANCEL_TRANSLATION_REASON = "Quitting, cancelling active translation"
POPUP_CLOSED_CANCEL_TRANSLATION_REASON = "Popup closed, cancelling active translation"
TARGET_LANGUAGE_CHANGED_CANCEL_REASON = "Target language changed, cancelling current translation"


def __getattr__(name: str) -> str:
    try:
        english, chinese = _TEXT[name]
    except KeyError:
        raise AttributeError(name) from None
    return tr(english, chinese)


def already_running_title() -> str:
    """Return the duplicate-launch notification title."""
    return tr("{app} is already running", "{app} 已在运行", app=APP_NAME)


def model_fallback_message(model: str) -> str:
    """Return a session fallback model notification message."""
    return tr("Using “{model}” for this session.", "本次使用“{model}”。", model=model)
