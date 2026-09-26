"""Interface language for user-facing text (English by default, or Chinese).

Each message is written once at its call site with both languages, e.g.
``tr("Copy translation", "复制译文")``, so wording stays next to the code that
shows it. The active language is set from settings at startup and when saved.
This module has no Qt or platform imports so core messages can use it too.
"""

from __future__ import annotations

from typing import Literal

InterfaceLanguage = Literal["en", "zh"]
INTERFACE_LANGUAGES: tuple[InterfaceLanguage, ...] = ("en", "zh")

_language: InterfaceLanguage = "en"


def set_language(language: str) -> None:
    global _language
    _language = "zh" if language == "zh" else "en"


def current_language() -> InterfaceLanguage:
    return _language


def tr(english: str, chinese: str, **values) -> str:
    """Return the text for the active interface language, formatted with ``values``."""
    text = chinese if _language == "zh" else english
    return text.format(**values) if values else text
