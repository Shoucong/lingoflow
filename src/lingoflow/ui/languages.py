"""Short, readable language names for the interface; stored values stay unchanged."""

from __future__ import annotations

LANGUAGE_NAMES = {
    "auto": "自动",
    "English": "英语",
    "Chinese(Simplified)": "简体中文",
    "Chinese(Traditional)": "繁体中文",
    "Japanese": "日语",
    "Spanish": "西班牙语",
    "French": "法语",
    "German": "德语",
    "Russian": "俄语",
    "Italian": "意大利语",
    "Korean": "韩语",
    "Thai": "泰语",
    "Vietnamese": "越南语",
}


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, language)
