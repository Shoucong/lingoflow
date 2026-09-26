"""Offline word lookup in the dictionaries that ship with macOS.

The public ``DCSCopyTextDefinition`` returns the first hit across every enabled
dictionary, so "ran" can come back as the Chinese headword 蚺 (rán) and
"inhibited" as an unrelated adjective. Like Easydict and Bob, this module uses
DictionaryServices' record API to query one dictionary by its identifier and
reads the entry XHTML. The dictionary's own index maps inflections to their
headwords (ran → run, mice → mouse, inhibited → inhibit).

These functions are not in the public SDK. They are loaded defensively: if a
future macOS removes them, ``available`` is False and callers fall back to model
translation instead of failing.
"""

from __future__ import annotations

import re
import threading
import xml.etree.ElementTree as ET

from lingoflow.core.dictionary import (
    DictionaryEntry,
    DictionaryResult,
    Example,
    PartOfSpeech,
    Pronunciation,
    Sense,
    word_script,
)
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

OXFORD_ENGLISH_CHINESE = "com.apple.dictionary.zh_CN-en.OCD"
OXFORD_AMERICAN_ENGLISH = "com.apple.dictionary.NOAD"
_FRAMEWORK = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks/DictionaryServices.framework"
)
_FUNCTIONS = [
    ("DCSCopyAvailableDictionaries", b"@"),
    ("DCSDictionaryGetIdentifier", b"@@"),
    ("DCSDictionaryGetName", b"@@"),
    ("DCSCopyRecordsForSearchString", b"@@@^v^v"),
    ("DCSRecordGetHeadword", b"@@"),
    ("DCSRecordCopyData", b"@@q"),
]
_XHTML = 0  # DCSRecordCopyData version returning the entry markup
_ENTRY_TAG = "{http://www.apple.com/DTDs/DictionaryService-1.0.rng}entry"
_CJK = re.compile(r"[㐀-鿿]")
# Sub-trees shown elsewhere or not at all in a compact card.
_NOT_SENSE_TEXT = {"exg", "eg", "pvsec", "pvg", "pvb", "infg", "etym", "note", "xrg"}


# ---------------------------------------------------------------------------
# XHTML helpers
# ---------------------------------------------------------------------------


def _classes(element) -> list[str]:
    return (element.get("class") or "").split()


def _has(element, name: str) -> bool:
    return name in _classes(element)


def _text(element, skip: frozenset[str] = frozenset({"ty_pinyin"})) -> str:
    parts: list[str] = []

    def walk(node, top: bool) -> None:
        if not top and skip.intersection(_classes(node)):
            if node.tail:
                parts.append(node.tail)
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child, False)
        if not top and node.tail:
            parts.append(node.tail)

    walk(element, True)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _collect(element, name: str, stop: set[str] = _NOT_SENSE_TEXT) -> list:
    """Descendants with class ``name``, not descending into ``stop`` sub-trees."""
    found = []
    for child in element:
        classes = _classes(child)
        if name in classes:
            found.append(child)
        elif not stop.intersection(classes):
            found.extend(_collect(child, name, stop))
    return found


def _clean(text: str) -> str:
    return text.strip().strip(";；,，").strip()


def _label(text: str) -> str:
    """Subject labels arrive as "Biology" or, on the Chinese side, as "［Physiology］"."""
    return _clean(text).strip("[]［］ ")


def _unique(values) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        if value and value not in seen:
            seen[value] = None
    return tuple(seen)


def _entry_element(markup: str):
    try:
        root = ET.fromstring(markup[markup.index("<html") :])
    except (ValueError, ET.ParseError) as error:
        logger.debug("Unreadable dictionary entry: %s", error)
        return None
    return next(root.iter(_ENTRY_TAG), None)


def _pronunciations(entry) -> tuple[Pronunciation, ...]:
    result = []
    for group in _collect(entry, "prx", stop={"gramb", "se1", "sg"} | _NOT_SENSE_TEXT):
        for phonetic in _collect(group, "ph"):
            ipa = _text(phonetic)
            if ipa:
                result.append(Pronunciation(group.get("dialect") or "", ipa))
    if not result:  # Chinese headwords carry pinyin instead
        for pinyin in _collect(entry, "pr", stop={"gramb"} | _NOT_SENSE_TEXT):
            if _text(pinyin):
                result.append(Pronunciation("", _text(pinyin)))
    return tuple(dict.fromkeys(result))


def _examples(block) -> tuple[Example, ...]:
    examples = []
    for group in _collect(block, "exg", stop={"pvsec", "pvg", "pvb"}):
        source = " ".join(_text(c) for c in _collect(group, "con", stop=set()))
        source = _clean(source) or _clean(
            " ".join(_text(c) for c in _collect(group, "ex", stop=set()))
        )
        translation = "；".join(
            _clean(_text(t))
            for t in _collect(group, "trans", stop=set())
            if not _has(t, "ty_pinyin")
        )
        if source:
            examples.append(Example(source, translation))
    return tuple(examples[:3])


def _bilingual_sense(block, number: str = "") -> Sense:
    translations = _unique(
        _clean(_text(t)) for t in _collect(block, "trans") if not _has(t, "ty_pinyin")
    )
    domains = _unique(_label(_text(f)) for f in _collect(block, "fld"))
    indicator = next((_clean(_text(i, frozenset({"gp"}))) for i in _collect(block, "ind")), "")
    return Sense(
        number=number,
        domains=domains,
        indicator=indicator,
        translations=translations,
        examples=_examples(block),
    )


def parse_bilingual(markup: str) -> DictionaryEntry | None:
    """Parse an Oxford English–Chinese / Chinese–English entry."""
    entry = _entry_element(markup)
    if entry is None:
        return None
    headwords = _collect(entry, "hw")
    headword = _text(headwords[0], frozenset({"pr", "ph", "prx", "ty_pinyin"})) if headwords else ""
    headword = headword or entry.get(
        "{http://www.apple.com/DTDs/DictionaryService-1.0.rng}title", ""
    )
    parts = []
    for gramb in _collect(entry, "gramb", stop={"pvsec", "pvg", "pvb"}):
        label = next((_clean(_text(p)) for p in _collect(gramb, "ps")), "")
        blocks = _collect(gramb, "semb")
        if blocks:
            senses = []
            for block in blocks:
                number = next(
                    (_clean(_text(n)) for n in _collect(block, "sn") if _has(n, "ty_label")), ""
                )
                sense = _bilingual_sense(block, number)
                if sense.translations:
                    senses.append(sense)
        else:
            sense = _bilingual_sense(gramb)
            senses = [sense] if sense.translations else []
        if senses:
            parts.append(PartOfSpeech(label, tuple(senses)))
    form_of = None
    if not parts:
        references = _collect(entry, "xr", stop=set())
        if references:
            target = _clean(_text(references[0], frozenset({"xrlabel", "xrlabelGroup", "gp"})))
            label = " ".join(
                _clean(_text(e))
                for e in _collect(entry, "ps", stop=set()) + _collect(entry, "gr", stop=set())
            )
            form_of = (label, target) if target else None
    return DictionaryEntry(
        headword=headword.strip(),
        pronunciations=_pronunciations(entry),
        parts=tuple(parts),
        form_of=form_of,
    )


def parse_monolingual(markup: str) -> DictionaryEntry | None:
    """Parse a New Oxford American Dictionary entry (definitions, no translations)."""
    entry = _entry_element(markup)
    if entry is None:
        return None
    headwords = _collect(entry, "hw")
    headword = _text(headwords[0]).replace("·", "") if headwords else ""
    parts = []
    for block in _collect(entry, "se1", stop={"etym", "note"}):
        label = next((_clean(_text(p)) for p in _collect(block, "pos", stop={"se2", "etym"})), "")
        senses = []
        for definition_block in _collect(block, "msDict", stop={"etym"}):
            definition = next((_clean(_text(d)) for d in _collect(definition_block, "df")), "")
            if not definition:
                continue
            domains = _unique(_clean(_text(s)) for s in _collect(definition_block, "sj"))
            examples = tuple(
                Example(_clean(_text(e)))
                for e in _collect(definition_block, "ex", stop=set())[:2]
                if _clean(_text(e))
            )
            senses.append(Sense(domains=domains, definition=definition, examples=examples))
        if senses:
            parts.append(PartOfSpeech(label, tuple(senses[:6])))
    return DictionaryEntry(
        headword=headword,
        pronunciations=_pronunciations(entry),
        parts=tuple(parts),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MacOSDictionaryService:
    """Look up single words in the Oxford dictionaries bundled with macOS."""

    def __init__(self) -> None:
        self._functions: dict | None = None
        self._dictionaries: dict[str, object] = {}
        self._names: dict[str, str] = {}
        self._lock = threading.Lock()

    def _load(self) -> dict | None:
        with self._lock:
            if self._functions is not None:
                return self._functions or None
            functions: dict = {}
            try:
                import objc
                from Foundation import NSBundle

                bundle = NSBundle.bundleWithPath_(_FRAMEWORK)
                objc.loadBundleFunctions(bundle, functions, _FUNCTIONS)
                missing = [name for name, _ in _FUNCTIONS if name not in functions]
                if missing:
                    raise RuntimeError(f"missing {', '.join(missing)}")
                for dictionary in functions["DCSCopyAvailableDictionaries"]() or []:
                    identifier = str(functions["DCSDictionaryGetIdentifier"](dictionary))
                    self._dictionaries[identifier] = dictionary
                    self._names[identifier] = str(functions["DCSDictionaryGetName"](dictionary))
            except Exception as error:
                logger.info("macOS dictionaries unavailable: %s", error)
                functions = {}
            self._functions = functions
            return functions or None

    def has_dictionary(self, identifier: str) -> bool:
        return self._load() is not None and identifier in self._dictionaries

    @property
    def available(self) -> bool:
        return self.has_dictionary(OXFORD_ENGLISH_CHINESE)

    def dictionary_name(self, identifier: str) -> str:
        self._load()
        return self._names.get(identifier, identifier).strip()

    def _records(self, identifier: str, word: str) -> list[tuple[str, str]]:
        functions = self._load()
        dictionary = self._dictionaries.get(identifier)
        if not functions or dictionary is None:
            return []
        records = functions["DCSCopyRecordsForSearchString"](dictionary, word, None, None) or []
        return [
            (
                str(functions["DCSRecordGetHeadword"](r) or ""),
                str(functions["DCSRecordCopyData"](r, _XHTML) or ""),
            )
            for r in records
        ]

    def lookup(self, word: str, target_language: str) -> DictionaryResult | None:
        """Return dictionary entries for one word, or None if no dictionary applies."""
        script = word_script(word)
        word = word.strip()
        if script == "latin" and target_language == "Chinese(Simplified)":
            result = self._lookup_bilingual(word, chinese_headwords=False)
            if result is None or not result.found:
                return self._lookup_monolingual(word) or result
            return result
        if script == "cjk" and target_language == "English":
            return self._lookup_bilingual(word, chinese_headwords=True)
        return None

    def _lookup_bilingual(self, word: str, chinese_headwords: bool) -> DictionaryResult | None:
        if not self.has_dictionary(OXFORD_ENGLISH_CHINESE):
            return None
        entries: list[DictionaryEntry] = []
        seen: set[str] = set()
        for headword, markup in self._records(OXFORD_ENGLISH_CHINESE, word):
            # One bilingual dictionary serves both directions; "ran" also matches the
            # Chinese headword "蚺 rán" through its pinyin.
            if bool(_CJK.search(headword)) != chinese_headwords:
                continue
            entry = parse_bilingual(markup)
            if entry is None:
                continue
            key = entry.headword.casefold() + ("#form" if entry.form_of else "")
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
        entries = self._fold_forms(entries)
        return DictionaryResult(
            query=word,
            source_name=self.dictionary_name(OXFORD_ENGLISH_CHINESE),
            bilingual=True,
            entries=tuple(entries),
        )

    @staticmethod
    def _fold_forms(entries: list[DictionaryEntry]) -> list[DictionaryEntry]:
        """Turn "ran: past tense → run" stubs into a note on the run entry."""
        full = [entry for entry in entries if entry.has_senses]
        for stub in (entry for entry in entries if entry.form_of and not entry.has_senses):
            label, target = stub.form_of
            for index, entry in enumerate(full):
                if entry.headword.casefold() == target.casefold() and entry.form_of is None:
                    full[index] = DictionaryEntry(
                        entry.headword, entry.pronunciations, entry.parts, (label, stub.headword)
                    )
                    break
        return full

    def _lookup_monolingual(self, word: str) -> DictionaryResult | None:
        if not self.has_dictionary(OXFORD_AMERICAN_ENGLISH):
            return None
        entries = []
        for _headword, markup in self._records(OXFORD_AMERICAN_ENGLISH, word)[:2]:
            entry = parse_monolingual(markup)
            if entry is not None and entry.has_senses:
                entries.append(entry)
        if not entries:
            return None
        return DictionaryResult(
            query=word,
            source_name=self.dictionary_name(OXFORD_AMERICAN_ENGLISH),
            bilingual=False,
            entries=tuple(entries),
        )
