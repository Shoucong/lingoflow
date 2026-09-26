"""Lossless source segmentation and immutable retry checkpoints."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextSegment:
    text: str
    separator: str

    @property
    def source(self) -> str:
        return self.text + self.separator


@dataclass(frozen=True)
class TranslationCheckpoint:
    fingerprint: str
    completed: tuple[str, ...] = ()
    total: int = 0


def fingerprint(text: str, profile: dict) -> str:
    payload = json.dumps([text, profile], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_text(text: str, byte_budget: int) -> tuple[TextSegment, ...]:
    """Prefer paragraphs/sentences and preserve every source character.

    UTF-8 bytes are a conservative input-token bound for byte-based tokenizers,
    not an exact tokenizer count. Prompt/output reserves are handled by the caller.
    """
    if byte_budget < 4:
        raise ValueError("The input budget is too small.")
    protected = [
        match.span()
        for match in re.finditer(
            r"\$\$[\s\S]*?\$\$|(?<!\\)\$[^\n$]+\$|\\\[[\s\S]*?\\\]|"
            r"\\\([\s\S]*?\\\)|```[\s\S]*?```|`[^`\n]+`|https?://\S+",
            text,
        )
    ]
    parts = []
    start = 0
    while start < len(text):
        end, size = start, 0
        while end < len(text):
            cost = len(text[end].encode("utf-8"))
            if size + cost > byte_budget:
                break
            size += cost
            end += 1
        if end < len(text):
            window = text[start:end]
            for pattern in [r"\n\s*\n", r"(?<=[.!?])\s+|(?<=[。！？])\s*", r"\s+"]:
                boundaries = [match.end() for match in re.finditer(pattern, window)]
                minimum = 0 if pattern == r"\n\s*\n" else len(window) // 3
                if boundaries and boundaries[-1] > minimum:
                    end = start + boundaries[-1]
                    break
        for left, right in protected:
            if left < end < right:
                if left <= start:
                    if len(text[start:right].encode("utf-8")) > byte_budget:
                        raise ValueError(
                            "A formula, code block or URL exceeds the input budget. "
                            "Increase context/output budgets."
                        )
                    end = right
                else:
                    end = left
                break
        source = text[start:end]
        body = source.rstrip()
        parts.append(TextSegment(body, source[len(body) :]))
        start = end
    return tuple(parts)
