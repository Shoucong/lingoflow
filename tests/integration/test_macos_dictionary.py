"""Real lookups in the Oxford dictionaries shipped with macOS (skipped when unavailable)."""

import sys
import time

import pytest

pytestmark = pytest.mark.macos


@pytest.fixture(scope="module")
def dictionary():
    if sys.platform != "darwin":
        pytest.skip("macOS dictionaries only")
    from lingoflow.infrastructure.macos.dictionary import MacOSDictionaryService

    service = MacOSDictionaryService()
    if not service.available:
        pytest.skip("Oxford English–Chinese dictionary is not enabled on this Mac")
    return service


@pytest.mark.parametrize(
    ("word", "headword"),
    [("inhibited", "inhibit"), ("mice", "mouse"), ("ran", "run"), ("criteria", "criterion")],
)
def test_inflected_forms_resolve_to_their_entry(dictionary, word, headword):
    result = dictionary.lookup(word, "Chinese(Simplified)")
    assert result.bilingual and result.found
    assert result.entries[0].headword == headword
    # Chinese headwords that share the pinyin (e.g. 蚺 rán) are not shown for English words.
    assert all(entry.headword.isascii() for entry in result.entries)


def test_irregular_form_is_explained(dictionary):
    entry = dictionary.lookup("ran", "Chinese(Simplified)").entries[0]
    assert entry.form_of == ("past tense", "ran")


def test_scientific_term_missing_from_the_bilingual_dictionary_falls_back(dictionary):
    result = dictionary.lookup("kinase", "Chinese(Simplified)")
    assert result is not None and not result.bilingual
    assert "enzyme" in result.entries[0].parts[0].senses[0].definition


def test_chinese_word_is_looked_up_for_an_english_target(dictionary):
    result = dictionary.lookup("抑制", "English")
    assert result.found
    translations = {t for p in result.entries[0].parts for s in p.senses for t in s.translations}
    assert "inhibit" in translations


def test_phrases_and_other_language_pairs_use_the_model(dictionary):
    assert dictionary.lookup("binding affinity", "Chinese(Simplified)") is None
    assert dictionary.lookup("kinase", "Japanese") is None


def test_lookups_are_fast_enough_to_run_on_the_ui_thread(dictionary):
    dictionary.lookup("warm", "Chinese(Simplified)")
    started = time.perf_counter()
    for word in ["inhibit", "mediate", "significant", "expression", "yield", "model"]:
        dictionary.lookup(word, "Chinese(Simplified)")
    assert (time.perf_counter() - started) / 6 < 0.05
