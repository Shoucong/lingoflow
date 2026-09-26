from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

from lingoflow.config.settings import AppSettings
from lingoflow.core.dictionary import (
    DictionaryEntry,
    DictionaryResult,
    Example,
    PartOfSpeech,
    Pronunciation,
    Sense,
)
from lingoflow.i18n import set_language
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.theme import colors
from lingoflow.ui.word_card import render_card


def entry(headword="suppress", senses=5, form_of=None):
    return DictionaryEntry(
        headword=headword,
        pronunciations=(Pronunciation("BrE", "səˈprɛs"), Pronunciation("AmE", "səˈprɛs")),
        parts=(
            PartOfSpeech(
                "transitive verb",
                tuple(
                    Sense(
                        number=f"({i + 1})",
                        domains=("Biology",) if i == 1 else (),
                        translations=(f"义项{i + 1}",),
                        examples=(Example(f"example {i + 1}", f"例句{i + 1}"),),
                    )
                    for i in range(senses)
                ),
            ),
        ),
        form_of=form_of,
    )


BILINGUAL = DictionaryResult("suppressed", "Test Oxford", True, (entry(),))
FALLBACK = DictionaryResult(
    "enzymes",
    "Test American",
    False,
    (
        DictionaryEntry(
            "enzyme",
            (Pronunciation("", "ˈenˌzīm"),),
            (PartOfSpeech("noun", (Sense(definition="a biological catalyst"),)),),
        ),
    ),
)


@pytest.fixture
def popup(qtbot, monkeypatch, tmp_path, own_popup):
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    widget = own_popup(TranslationPopup(AppSettings(), window_state_path=tmp_path / "w.json"))
    widget.show_with_text("suppressed")
    return widget


def shown(widget) -> bool:
    return widget.isVisibleTo(widget.window())


def test_card_shows_headword_senses_science_label_source_and_collapses_long_entries():
    html = render_card(BILINGUAL, colors("light"), 14)
    assert "suppress" in html and "suppressed → suppress" in html
    assert "UK" in html and "US" in html and "speak:en-GB:suppress" in html
    assert "义项1" in html and "义项3" in html and "义项4" not in html
    assert "2 more senses" in html and "more:0:0" in html
    assert "Biology" in html and "font-weight:600" in html
    assert "Source: Test Oxford" in html
    expanded = render_card(BILINGUAL, colors("light"), 14, expanded={"0:0"})
    assert "义项5" in expanded and "more senses" not in expanded


def test_card_explains_irregular_forms_in_the_interface_language():
    result = DictionaryResult("swam", "D", True, (entry("swim", 1, ("past tense", "swam")),))
    assert "swam is the past tense of swim" in render_card(result, colors("light"), 14)
    set_language("zh")
    assert "swam 是 swim 的过去式" in render_card(result, colors("light"), 14)


def test_model_gloss_is_labelled_and_leads_only_when_the_dictionary_lacks_a_translation():
    pending = render_card(BILINGUAL, colors("light"), 14, gloss_state="pending")
    assert "Model gloss (no sentence context)" in pending and "translating…" in pending
    done = render_card(FALLBACK, colors("light"), 14, gloss="酶", gloss_state="done")
    assert done.index("enzyme") < done.index("Model translation") < done.index("a biological")
    assert "speak:en-US:enzyme" in done


def test_popup_word_card_replaces_the_source_excerpt_and_keeps_the_gloss_separate(popup):
    popup.show_dictionary(BILINGUAL)
    assert popup.is_word_card
    assert not shown(popup.text_splitter.source_panel)
    assert not shown(popup.stop_btn) and not shown(popup.speak_translation_btn)
    assert shown(popup.copy_btn)
    popup.start_translation()
    popup.append_translation("抑制")
    assert "抑制" not in popup.translation_text.toPlainText()  # shown once complete
    popup.finish_translation()
    text = popup.translation_text.toPlainText()
    assert "suppress" in text and "抑制" in text
    popup.copy_btn.click()
    assert QApplication.clipboard().text() == text


def test_card_links_play_pronunciation_and_expand_senses(popup, monkeypatch):
    spoken = []
    monkeypatch.setattr(popup.speech, "speak", spoken.append)
    popup.show_dictionary(BILINGUAL, expect_gloss=False)
    popup._on_card_link(QUrl("speak:en-GB:suppress"))
    assert (spoken[0].text, spoken[0].locale) == ("suppress", "en-GB")
    assert "义项5" not in popup.translation_text.toPlainText()
    popup._on_card_link(QUrl("more:0:0"))
    assert "义项5" in popup.translation_text.toPlainText()


def test_failed_gloss_keeps_the_card_and_new_text_leaves_word_mode(popup):
    popup.show_dictionary(BILINGUAL)
    popup.start_translation()
    popup.show_error("Model offline")
    assert "unavailable" in popup.translation_text.toPlainText()
    assert "义项1" in popup.translation_text.toPlainText()
    popup.show_with_text("A whole sentence to translate.")
    assert not popup.is_word_card
    assert shown(popup.text_splitter.source_panel)


def test_translate_with_model_is_offered_only_for_word_cards(popup, qtbot):
    popup.more_menu.aboutToShow.emit()
    assert not popup.model_translate_action.isVisible()
    popup.show_dictionary(BILINGUAL)
    assert popup.model_translate_action.isVisible()
    with qtbot.waitSignal(popup.model_translation_requested) as requested:
        popup.model_translate_action.trigger()
    assert requested.args == ["suppressed"]
    popup.leave_word_mode()
    assert not popup.is_word_card and popup.translation_text.toPlainText() == ""


def test_word_in_no_dictionary_says_so_and_leads_with_the_model_translation():
    miss = DictionaryResult("equivariance", "", False)
    html = render_card(miss, colors("light"), 14, gloss="等变性", gloss_state="done")
    assert "Not in the macOS dictionaries" in html
    assert html.index("equivariance") < html.index("Model translation") < html.index("等变性")
    assert "Source:" not in html
