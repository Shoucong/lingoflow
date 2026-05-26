"""Protocol interfaces for app side effects."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from lingoflow.config.settings import AppSettings
from lingoflow.core.hotkey import HotkeyAction
from lingoflow.core.ocr import OCRResult


@runtime_checkable
class ClipboardPort(Protocol):
    """Reads selected text from the frontmost app."""

    def get_selected_text(self) -> str:
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
    ) -> Iterator[str]:
        """Yield translated text chunks."""

    def cancel(self) -> None:
        """Cancel any active provider work."""

    def update_settings(self, settings: AppSettings) -> None:
        """Apply validated app settings."""


@runtime_checkable
class OCRBackend(Protocol):
    """OCR capture and recognition backend."""

    def capture_interactive(self) -> Path | None:
        """Let the user select a screen region and return the capture path."""

    def extract_text(self, image_path: Path) -> OCRResult:
        """Extract text from a captured image."""

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
