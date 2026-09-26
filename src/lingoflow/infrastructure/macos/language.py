"""Local source-language identification for translation models requiring a language name."""

from __future__ import annotations

import re

LANGUAGES = {
    "en": "English",
    "zh-Hans": "Chinese(Simplified)",
    "zh-Hant": "Chinese(Traditional)",
    "ja": "Japanese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ru": "Russian",
    "it": "Italian",
    "ko": "Korean",
    "th": "Thai",
    "vi": "Vietnamese",
}


def detect_source_language(text: str) -> str | None:
    """Use macOS locally; treat isolated Latin scientific terms as English.

    An explicit Text Source always bypasses this reading-oriented fallback. A lone
    Latin word such as 'kinase' has too little context for reliable language ID.
    """
    from Foundation import NSLinguisticTagger

    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", text.strip()):
        return "English"
    language = NSLinguisticTagger.dominantLanguageForString_(text)
    if language in LANGUAGES:
        return LANGUAGES[language]
    if language in {None, "und"} and re.search(r"[A-Za-z]", text):
        return "English"
    return None
