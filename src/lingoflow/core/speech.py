"""Speech requests and deterministic installed-voice selection."""

from __future__ import annotations

import re
from dataclasses import dataclass

LANGUAGE_LOCALES = {
    "English": "en-US",
    "Chinese(Simplified)": "zh-CN",
    "Chinese(Traditional)": "zh-TW",
    "Japanese": "ja-JP",
    "Spanish": "es-ES",
    "French": "fr-FR",
    "German": "de-DE",
    "Russian": "ru-RU",
    "Italian": "it-IT",
    "Korean": "ko-KR",
    "Thai": "th-TH",
    "Vietnamese": "vi-VN",
}


@dataclass(frozen=True)
class SpeechVoice:
    name: str
    locale: str


@dataclass(frozen=True)
class SpeechRequest:
    owner: str
    kind: str
    text: str
    locale: str
    voice: str = ""
    rate: int = 175


def parse_voices(output: str) -> list[SpeechVoice]:
    voices = []
    for line in output.splitlines():
        match = re.match(r"^(.+?)\s+([a-z]{2,3}[_-][A-Z]{2})\s*(?:#|$)", line)
        if match:
            voices.append(SpeechVoice(match[1].strip(), match[2].replace("_", "-")))
    return voices


def choose_voice(voices: list[SpeechVoice], locale: str, preferred: str = "") -> SpeechVoice:
    compatible = [voice for voice in voices if voice.locale == locale]
    if preferred:
        for voice in compatible:
            if voice.name == preferred:
                return voice
        raise ValueError(f"Voice '{preferred}' is unavailable for {locale}. Choose Automatic.")
    defaults = {"en-US": "Samantha", "en-GB": "Daniel", "zh-CN": "Tingting", "zh-TW": "Meijia"}
    for name in [defaults.get(locale), "Alex", "Ava", "Eddy", "Sandy", "Reed", "Flo"]:
        for voice in compatible:
            if voice.name.split(" (")[0] == name:
                return voice
    novelty = {
        "Albert",
        "Bad News",
        "Bahh",
        "Bells",
        "Boing",
        "Bubbles",
        "Cellos",
        "Good News",
        "Jester",
        "Organ",
        "Trinoids",
        "Whisper",
        "Wobble",
        "Zarvox",
    }
    ordinary = [voice for voice in compatible if voice.name not in novelty]
    if ordinary:
        return ordinary[0]
    raise ValueError(
        f"No suitable installed voice for {locale}. Download one in macOS Accessibility settings."
    )
