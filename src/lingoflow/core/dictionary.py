"""Dictionary entries for single-word lookups; no platform or Qt imports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]{0,39}")
_CJK_WORD = re.compile(r"[㐀-鿿]{1,6}")


def word_script(text: str) -> str | None:
    """Return "latin" or "cjk" when ``text`` is one word worth a dictionary lookup."""
    word = text.strip()
    if _LATIN_WORD.fullmatch(word) and not word.endswith(("-", "'", "’")):
        return "latin"
    if _CJK_WORD.fullmatch(word):
        return "cjk"
    return None


@dataclass(frozen=True)
class Example:
    source: str
    translation: str = ""


@dataclass(frozen=True)
class Sense:
    number: str = ""
    domains: tuple[str, ...] = ()
    indicator: str = ""
    translations: tuple[str, ...] = ()
    definition: str = ""  # monolingual dictionaries define instead of translating
    examples: tuple[Example, ...] = ()


@dataclass(frozen=True)
class PartOfSpeech:
    label: str
    senses: tuple[Sense, ...]


@dataclass(frozen=True)
class Pronunciation:
    dialect: str  # "BrE", "AmE" or "" when the dictionary gives one form
    ipa: str


@dataclass(frozen=True)
class DictionaryEntry:
    headword: str
    pronunciations: tuple[Pronunciation, ...] = ()
    parts: tuple[PartOfSpeech, ...] = ()
    # e.g. ("past tense", "run") when the searched form points to another entry
    form_of: tuple[str, str] | None = None

    @property
    def has_senses(self) -> bool:
        return any(part.senses for part in self.parts)


@dataclass(frozen=True)
class DictionaryResult:
    query: str
    source_name: str
    bilingual: bool
    entries: tuple[DictionaryEntry, ...] = field(default_factory=tuple)

    @property
    def found(self) -> bool:
        return any(entry.has_senses for entry in self.entries)

    def plain_text(self) -> str:
        """Plain text of the entries, as shown, for copying."""
        lines: list[str] = []
        for entry in self.entries:
            phonetics = "  ".join(
                f"{p.dialect} /{p.ipa}/" if p.dialect else f"/{p.ipa}/"
                for p in entry.pronunciations
            )
            lines.append(f"{entry.headword}  {phonetics}".rstrip())
            for part in entry.parts:
                if part.label:
                    lines.append(part.label)
                for sense in part.senses:
                    meaning = "；".join(sense.translations) or sense.definition
                    prefix = f"{sense.number} " if sense.number else ""
                    domains = f"[{', '.join(sense.domains)}] " if sense.domains else ""
                    lines.append(f"{prefix}{domains}{meaning}".rstrip())
                    for example in sense.examples:
                        lines.append(f"  ▸ {example.source}  {example.translation}".rstrip())
            lines.append("")
        return "\n".join(lines).strip()
