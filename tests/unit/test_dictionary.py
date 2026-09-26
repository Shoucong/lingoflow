"""Dictionary parsing on synthetic entries shaped like the macOS Oxford dictionaries."""

from lingoflow.core.dictionary import DictionaryResult, word_script
from lingoflow.infrastructure.macos.dictionary import (
    MacOSDictionaryService,
    parse_bilingual,
    parse_monolingual,
)

HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?><html '
    'xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng"><body>'
)
TAIL = "</body></html>"

BILINGUAL = (
    HEAD
    + '<d:entry id="x1" d:title="suppress" class="entry">'
    '<span class="hwg"><span class="hw">suppress </span>'
    '<span dialect="BrE" class="prx"><span class="ph">səˈprɛs</span></span>'
    '<span dialect="AmE" class="prx"><span class="ph">səˈprɛs</span></span></span>'
    '<span class="gramb"><span class="x_xdh"><span class="ps">transitive verb</span></span>'
    '<span class="semb"><span class="gp sn ty_label">① </span>'
    '<span class="trg"><span class="ind">'
    '<span class="gp">(</span>hold back<span class="gp">) </span></span>'
    '<span class="trans">压制 </span><span class="trans ty_pinyin">yāzhì </span></span>'
    '<span class="trg"><span class="trans">阻止 </span></span>'
    '<span class="exg"><span class="con">to suppress a cough</span>'
    '<span class="trg"><span class="trans">忍住咳嗽</span></span></span></span>'
    '<span class="semb"><span class="gp sn ty_label">② </span>'
    '<span class="trg"><span class="fld">Biology</span><span class="trans">抑制 </span></span>'
    "</span></span></d:entry>" + TAIL
)

FORM_STUB = (
    HEAD
    + '<d:entry id="x2" d:title="swam" class="entry"><span class="hwg">'
    '<span class="hw">swam </span></span><span class="gramb"><span class="ps">past tense</span>'
    '<span class="xrg"><span class="xr">swim<span class="xrlabel"> A</span></span></span>'
    "</span></d:entry>" + TAIL
)

MONOLINGUAL = (
    HEAD
    + '<d:entry id="x3" class="entry"><span class="hg"><span class="hw">en·zyme</span>'
    '<span class="prx"><span class="ph">ˈenˌzīm</span></span></span><span class="sg">'
    '<span class="se1"><span class="posg"><span class="pos">noun</span></span>'
    '<span class="se2"><span class="msDict"><span class="sj">Biochemistry</span>'
    '<span class="df">a substance that speeds up a reaction in a living thing</span>'
    '<span class="eg"><span class="ex">an example sentence</span></span></span></span>'
    '</span></span><span class="etym">ORIGIN not shown</span></d:entry>' + TAIL
)


def test_single_words_are_detected_but_phrases_are_not():
    assert word_script("kinase") == "latin"
    assert word_script(" well-known ") == "latin"
    assert word_script("抑制") == "cjk"
    assert word_script("two words") is None
    assert word_script("IC50") is None
    assert word_script("") is None


def test_bilingual_entry_keeps_senses_domains_examples_and_both_pronunciations():
    entry = parse_bilingual(BILINGUAL)
    assert entry.headword == "suppress"
    assert [(p.dialect, p.ipa) for p in entry.pronunciations] == [
        ("BrE", "səˈprɛs"),
        ("AmE", "səˈprɛs"),
    ]
    part = entry.parts[0]
    assert part.label == "transitive verb"
    first, second = part.senses
    assert first.number == "①" and first.translations == ("压制", "阻止")
    assert first.indicator == "hold back"
    assert first.examples[0].source == "to suppress a cough"
    assert first.examples[0].translation == "忍住咳嗽"
    # Pinyin is not a translation; subject labels are kept separately.
    assert "yāzhì" not in first.translations
    assert second.domains == ("Biology",) and second.translations == ("抑制",)


def test_form_pointer_is_folded_into_the_entry_it_points_to():
    stub = parse_bilingual(FORM_STUB)
    assert not stub.has_senses
    assert stub.form_of == ("past tense", "swim")
    target = parse_bilingual(BILINGUAL.replace("suppress", "swim"))
    folded = MacOSDictionaryService._fold_forms([stub, target])
    assert [entry.headword for entry in folded] == ["swim"]
    assert folded[0].form_of == ("past tense", "swam")


def test_monolingual_entry_gives_definitions_without_the_etymology():
    entry = parse_monolingual(MONOLINGUAL)
    assert entry.headword == "enzyme"
    sense = entry.parts[0].senses[0]
    assert entry.parts[0].label == "noun"
    assert sense.domains == ("Biochemistry",)
    assert sense.definition.startswith("a substance")
    assert "ORIGIN" not in sense.definition


def test_plain_text_matches_the_card_content_for_copying():
    result = DictionaryResult("suppressed", "Test Dictionary", True, (parse_bilingual(BILINGUAL),))
    text = result.plain_text()
    assert text.startswith("suppress  BrE /səˈprɛs/  AmE /səˈprɛs/")
    assert "① 压制；阻止" in text and "② [Biology] 抑制" in text


def test_unreadable_markup_is_ignored():
    assert parse_bilingual("<html><body><broken") is None
