"""Application state primitives for workflow coordination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock


class AppState(Enum):
    """High-level state for the menu bar app."""

    IDLE = "idle"
    CAPTURING = "capturing"
    OCR_RECOGNIZING = "ocr_recognizing"
    TRANSLATING = "translating"
    CANCELLING = "cancelling"
    ERROR = "error"
    ONBOARDING = "onboarding"


BUSY_STATES = {
    AppState.CAPTURING,
    AppState.OCR_RECOGNIZING,
    AppState.TRANSLATING,
    AppState.CANCELLING,
    AppState.ONBOARDING,
}

OCR_STATES = {
    AppState.CAPTURING,
    AppState.OCR_RECOGNIZING,
}

STATUS_LABELS = {
    AppState.IDLE: "Ready",
    AppState.CAPTURING: "Capturing...",
    AppState.OCR_RECOGNIZING: "Recognizing...",
    AppState.TRANSLATING: "Translating...",
    AppState.CANCELLING: "Cancelling...",
    AppState.ERROR: "Error",
    AppState.ONBOARDING: "Onboarding",
}


@dataclass(frozen=True)
class AppStateSnapshot:
    """Immutable view of app state at a moment in time."""

    state: AppState
    detail: str | None = None

    @property
    def is_busy(self) -> bool:
        """Return whether the app is handling an active workflow."""
        return self.state in BUSY_STATES

    @property
    def is_translating(self) -> bool:
        """Return whether translation output can still arrive."""
        return self.state == AppState.TRANSLATING

    @property
    def is_ocr_active(self) -> bool:
        """Return whether an OCR capture or recognition workflow is active."""
        return self.state in OCR_STATES

    @property
    def status_label(self) -> str:
        """Return the default tray/status text for this state."""
        return self.detail or STATUS_LABELS[self.state]


class AppStateTracker:
    """Small thread-safe holder for the current app state."""

    def __init__(self, initial: AppState = AppState.IDLE) -> None:
        self._state = initial
        self._detail: str | None = None
        self._lock = RLock()

    @property
    def current(self) -> AppState:
        """Return the current state."""
        with self._lock:
            return self._state

    @property
    def detail(self) -> str | None:
        """Return optional state detail."""
        with self._lock:
            return self._detail

    @property
    def is_busy(self) -> bool:
        """Return whether the app is handling an active workflow."""
        return self.snapshot().is_busy

    @property
    def is_translating(self) -> bool:
        """Return whether translation output can still arrive."""
        return self.snapshot().is_translating

    @property
    def is_ocr_active(self) -> bool:
        """Return whether OCR capture or recognition is active."""
        return self.snapshot().is_ocr_active

    @property
    def status_label(self) -> str:
        """Return the default tray/status text for the current state."""
        return self.snapshot().status_label

    def set(self, state: AppState, detail: str | None = None) -> AppStateSnapshot:
        """Set the current state and return a snapshot."""
        with self._lock:
            self._state = state
            self._detail = detail
            return AppStateSnapshot(state=self._state, detail=self._detail)

    def reset(self) -> AppStateSnapshot:
        """Return the app to idle."""
        return self.set(AppState.IDLE)

    def mark_error(self, detail: str | None = None) -> AppStateSnapshot:
        """Move the app to an error state."""
        return self.set(AppState.ERROR, detail=detail)

    def snapshot(self) -> AppStateSnapshot:
        """Return an immutable state snapshot."""
        with self._lock:
            return AppStateSnapshot(state=self._state, detail=self._detail)
