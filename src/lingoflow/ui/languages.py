"""Short, readable language names for the interface; stored values stay unchanged."""

from __future__ import annotations

from lingoflow.i18n import current_language

LANGUAGE_NAMES = {
    "auto": ("Auto", "自动"),
    "English": ("English", "英语"),
    "Chinese(Simplified)": ("Chinese (Simplified)", "简体中文"),
    "Chinese(Traditional)": ("Chinese (Traditional)", "繁体中文"),
    "Japanese": ("Japanese", "日语"),
    "Spanish": ("Spanish", "西班牙语"),
    "French": ("French", "法语"),
    "German": ("German", "德语"),
    "Russian": ("Russian", "俄语"),
    "Italian": ("Italian", "意大利语"),
    "Korean": ("Korean", "韩语"),
    "Thai": ("Thai", "泰语"),
    "Vietnamese": ("Vietnamese", "越南语"),
}


def language_name(language: str) -> str:
    names = LANGUAGE_NAMES.get(language)
    if names is None:
        return language
    return names[1] if current_language() == "zh" else names[0]
