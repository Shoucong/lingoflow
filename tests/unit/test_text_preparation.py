from __future__ import annotations

import pytest

from lingoflow.core.text_preparation import split_text


@pytest.mark.parametrize(
    "source",
    [
        "",
        "  hello world\r\n\r\nmore text  ",
        "无空格的长中文段落🧬" * 40,
        "A sentence. Another sentence!\n\n" * 70,
        "word" * 300,
        " \n\t" * 50,
    ],
)
def test_segmentation_preserves_every_character_and_respects_byte_budget(source):
    parts = split_text(source, 64)
    assert "".join(part.source for part in parts) == source
    assert all(len(part.source.encode("utf-8")) <= 64 for part in parts)


def test_formulas_are_not_split_across_requests():
    formula = r"$x^2 + y^2 = z^2$"
    source = "Prefix " * 6 + formula + " suffix" * 8
    parts = split_text(source, 64)
    assert "".join(part.source for part in parts) == source
    assert any(formula in part.text for part in parts)


def test_oversized_protected_content_has_an_explicit_error():
    with pytest.raises(ValueError, match="exceeds"):
        split_text("$" + "x" * 100 + "$", 64)
