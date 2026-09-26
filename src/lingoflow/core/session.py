"""UI-independent state for one translation request."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from lingoflow.core.text_preparation import TranslationCheckpoint


class SessionStatus(str, Enum):
    REVIEW = "review"
    ACQUIRING = "acquiring"
    TRANSLATING = "translating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranslationSession:
    request_id: int
    source_text: str = ""
    target_language: str = ""
    status: SessionStatus = SessionStatus.ACQUIRING
    translated_text: str = ""
    error: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    first_text_at: float | None = None
    finished_at: float | None = None
    checkpoint: TranslationCheckpoint | None = None

    def append(self, request_id: int, text: str) -> bool:
        if request_id != self.request_id or self.status != SessionStatus.TRANSLATING:
            return False
        if text and self.first_text_at is None:
            self.first_text_at = time.monotonic()
        self.translated_text += text
        return True

    def finish(self, status: SessionStatus, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self.finished_at = time.monotonic()
