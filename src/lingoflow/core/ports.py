"""Protocol interfaces for app side effects."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lingoflow.core.models import HotkeyAction, ModelChunk, ModelInfo, OCRResult
from lingoflow.core.text_preparation import TranslationCheckpoint

if TYPE_CHECKING:
    from lingoflow.config.settings import AppSettings


class ChatProvider(Protocol):
    """Text generation transport injected into the translation service."""

    def chat_stream(
        self,
        message: str,
        model: str,
        system_prompt: str | None = None,
        cancel_check: Callable[[], bool] | None = None,
        *,
        options: dict | None = None,
        keep_alive: int | None = None,
        think: bool | None = None,
        raw: bool = False,
    ) -> Iterator[ModelChunk]: ...

    def cancel(self) -> None: ...

    def is_available(self) -> bool: ...

    def list_models(self) -> list[ModelInfo]: ...


@runtime_checkable
class ClipboardPort(Protocol):
    """Reads selected text from the frontmost app."""

    def get_selected_text(self, cancel_check: Callable[[], bool] | None = None) -> str | None:
        """Return currently selected text, or an empty string."""


@runtime_checkable
class LLMProvider(Protocol):
    """Translation provider used by app workflows."""

    def is_available(self) -> bool:
        """Return whether the provider is reachable."""

    def get_available_models(self) -> list[str]:
        """Return available model names."""

    def translate_stream(
        self,
        text: str,
        target_language: str | None = None,
        source_language: str | None = None,
        on_chunk: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        checkpoint: TranslationCheckpoint | None = None,
        on_checkpoint: Callable[[TranslationCheckpoint], None] | None = None,
        on_source_detected: Callable[[str], None] | None = None,
    ) -> Iterator[str]:
        """Yield translated text chunks."""

    def cancel(self) -> None:
        """Cancel any active provider work."""

    def update_settings(self, settings: AppSettings) -> None:
        """Apply validated app settings."""


@runtime_checkable
class OCRBackend(Protocol):
    """OCR capture and recognition backend."""

    def capture_interactive(self, cancel_check: Callable[[], bool] | None = None) -> Path | None:
        """Let the user select a screen region and return the capture path."""

    def extract_text(
        self,
        image_path: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> OCRResult:
        """Extract text from a captured image."""

    def cancel(self) -> None:
        """Stop active capture/recognition if supported."""

    def cleanup_capture(self, image_path: Path | str) -> bool:
        """Remove a managed capture path when retention is disabled."""

    def update_settings(self, settings: AppSettings) -> None:
        """Apply validated app settings."""


@runtime_checkable
class HotkeyBackend(Protocol):
    """Global hotkey backend."""

    def register(
        self,
        action: HotkeyAction,
        hotkey: str,
        callback: Callable[[], None],
        description: str = "",
    ) -> None:
        """Register one hotkey callback."""

    def start(self) -> None:
        """Start listening for hotkeys."""

    def stop(self) -> None:
        """Stop listening for hotkeys."""

    def is_running(self) -> bool:
        """Return whether the backend is listening."""

    def update_settings(self, settings: AppSettings) -> None:
        """Apply validated app settings."""


@runtime_checkable
class PermissionServicePort(Protocol):
    """Permission service used by onboarding and app startup."""

    def required_permissions_ready(self) -> bool:
        """Return whether required permissions are usable."""


@runtime_checkable
class Notifier(Protocol):
    """User-facing notification/status output."""

    def show_notification(self, title: str, message: str) -> None:
        """Show a user-facing notification."""

    def update_status(self, status: str) -> None:
        """Update visible app status."""
