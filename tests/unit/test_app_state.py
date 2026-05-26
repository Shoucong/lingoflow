from __future__ import annotations

from lingoflow.core.app_state import AppState, AppStateSnapshot, AppStateTracker


def test_app_state_tracker_starts_idle() -> None:
    tracker = AppStateTracker()

    assert tracker.current == AppState.IDLE
    assert tracker.status_label == "Ready"
    assert tracker.is_busy is False
    assert tracker.is_translating is False
    assert tracker.is_ocr_active is False


def test_app_state_tracker_marks_translation_busy() -> None:
    tracker = AppStateTracker()

    snapshot = tracker.set(AppState.TRANSLATING)

    assert snapshot == AppStateSnapshot(AppState.TRANSLATING)
    assert tracker.current == AppState.TRANSLATING
    assert tracker.status_label == "Translating..."
    assert tracker.is_busy is True
    assert tracker.is_translating is True
    assert tracker.is_ocr_active is False


def test_app_state_tracker_tracks_ocr_capture_and_recognition() -> None:
    tracker = AppStateTracker()

    capture = tracker.set(AppState.CAPTURING)
    recognizing = tracker.set(AppState.OCR_RECOGNIZING)

    assert capture.is_ocr_active is True
    assert capture.status_label == "Capturing..."
    assert recognizing.is_ocr_active is True
    assert recognizing.status_label == "Recognizing..."
    assert tracker.is_busy is True


def test_app_state_tracker_reset_returns_idle() -> None:
    tracker = AppStateTracker(AppState.TRANSLATING)

    snapshot = tracker.reset()

    assert snapshot.state == AppState.IDLE
    assert tracker.current == AppState.IDLE
    assert tracker.is_busy is False


def test_app_state_tracker_error_detail_overrides_status_label() -> None:
    tracker = AppStateTracker()

    snapshot = tracker.mark_error("Ollama offline")

    assert snapshot.state == AppState.ERROR
    assert snapshot.detail == "Ollama offline"
    assert snapshot.status_label == "Ollama offline"
    assert tracker.status_label == "Ollama offline"
