"""Centralized user-facing UI messages (log-only reasons stay in English)."""

from __future__ import annotations

from lingoflow.config.constants import APP_NAME

HOTKEYS_UNAVAILABLE_TITLE = "快捷键不可用"
HOTKEYS_PERMISSION_RESTART = "请在系统设置中允许“辅助功能”和“输入监控”，然后重新启动 LingoFlow。"

OLLAMA_NOT_RUNNING_TITLE = "Ollama 未运行"
OLLAMA_START_COMMAND = "请先启动 Ollama（ollama serve）。"
OLLAMA_START_COMMAND_FOR_TRANSLATION = "翻译需要本机的 Ollama，请先启动（ollama serve）。"
OLLAMA_OFFLINE_STATUS = "Ollama offline"
OLLAMA_CONNECT_TRANSLATION_ERROR = "无法连接 Ollama。\n请确认它正在运行：ollama serve"

NO_TEXT_SELECTED_TITLE = "没有选中文字"
NO_TEXT_SELECTED_MESSAGE = "请先选中要翻译的文字，再按快捷键。"
SELECTION_UNAVAILABLE_TITLE = "无法读取选中文字"
SELECTION_UNAVAILABLE_MESSAGE = "请检查“辅助功能”权限。"

OCR_ERROR_TITLE = "截图识别失败"
OCR_FAILED_MESSAGE = "截图识别失败。"
NO_TEXT_FOUND_TITLE = "没有识别到文字"
NO_TEXT_FOUND_MESSAGE = "所选区域中没有可识别的文字。"

MODEL_NOT_FOUND_TITLE = "找不到翻译模型"
MODEL_NOT_FOUND_MESSAGE = "请在“设置 → 模型与高级”中选择已安装的模型，或在 Ollama 中安装当前模型。"

ALREADY_RUNNING_MESSAGE = "请使用菜单栏图标翻译、截图识别或打开设置。"

QUIT_CANCEL_TRANSLATION_REASON = "Quitting, cancelling active translation"
POPUP_CLOSED_CANCEL_TRANSLATION_REASON = "Popup closed, cancelling active translation"
TARGET_LANGUAGE_CHANGED_CANCEL_REASON = "Target language changed, cancelling current translation"


def already_running_title() -> str:
    """Return the duplicate-launch notification title."""
    return f"{APP_NAME} 已在运行"


def model_fallback_message(model: str) -> str:
    """Return a session fallback model notification message."""
    return f"本次使用“{model}”。"
