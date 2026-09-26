from __future__ import annotations

import pytest

from lingoflow.core.speech import SpeechVoice, choose_voice, parse_voices


def test_voice_parser_preserves_names_with_spaces_and_normalizes_locale():
    voices = parse_voices("Bad News en_US # test\nEddy (English (UK)) en_GB # hello\ninvalid")
    assert voices == [SpeechVoice("Bad News", "en-US"), SpeechVoice("Eddy (English (UK))", "en-GB")]


def test_automatic_voice_prefers_normal_speech_and_exact_accent():
    voices = [
        SpeechVoice("Bad News", "en-US"),
        SpeechVoice("Samantha", "en-US"),
        SpeechVoice("Daniel", "en-GB"),
    ]
    assert choose_voice(voices, "en-US").name == "Samantha"
    assert choose_voice(voices, "en-GB").name == "Daniel"
    with pytest.raises(ValueError, match="unavailable"):
        choose_voice(voices, "en-GB", "Samantha")
    with pytest.raises(ValueError, match="Download"):
        choose_voice(voices, "zh-CN")


def test_modern_named_voice_is_preferred_over_novelty_fallback():
    voices = [SpeechVoice("Wobble", "en-US"), SpeechVoice("Eddy (English (US))", "en-US")]
    assert choose_voice(voices, "en-US").name == "Eddy (English (US))"
