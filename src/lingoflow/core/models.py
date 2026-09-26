"""Shared data types with no GUI, transport or native framework imports."""

from dataclasses import dataclass
from enum import Enum


class HotkeyAction(Enum):
    TRANSLATE = "translate"
    OCR = "ocr"
    PRONOUNCE = "pronounce"
    WORD_LOOKUP = "word_lookup"


@dataclass(frozen=True)
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height


@dataclass
class OCRResult:
    text: str
    confidence: float | None = None
    source_image_path: str | None = None
    success: bool = True
    error_message: str | None = None
    cancelled: bool = False


@dataclass
class ModelChunk:
    content: str
    done: bool
    done_reason: str | None = None


@dataclass
class ModelInfo:
    name: str
    size: int
    modified_at: str


@dataclass
class ModelResponse:
    content: str
    model: str
    done: bool
    total_duration: int | None = None
    eval_count: int | None = None
