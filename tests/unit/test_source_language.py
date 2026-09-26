"""Real local macOS language identification, including short scientific terms."""

import pytest

pytest.importorskip("Foundation")

from lingoflow.infrastructure.macos.language import detect_source_language


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The docking score does not demonstrate binding affinity.", "English"),
        ("これは安全性の証拠ではありません。", "Japanese"),
        ("これは IC50 の値であり、Ki と同じではありません。", "Japanese"),
        ("这是简体中文。", "Chinese(Simplified)"),
        ("這是繁體中文。", "Chinese(Traditional)"),
        ("kinase", "English"),
        ("IC50", "English"),
    ],
)
def test_detects_reading_languages_locally(text, expected):
    assert detect_source_language(text) == expected
