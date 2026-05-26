# ruff: noqa: N802 - Qt-compatible fakes intentionally mirror camelCase APIs.

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from lingoflow.config.settings import AppSettings
from lingoflow.core.ocr import OCRResult, ScreenCaptureError
from lingoflow.infrastructure.ollama_client import OllamaError
from lingoflow.ui import main_window, messages, tray_controller
from lingoflow.ui.main_window import MainController


class FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class FakeTrayIcon:
    class MessageIcon:
        Information = object()

    def __init__(self) -> None:
        self.tooltip = ""
        self.menu = None
        self.visible = False
        self.messages: list[tuple[str, str]] = []

    def setIcon(self, icon) -> None:
        self.icon = icon

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def setContextMenu(self, menu) -> None:
        self.menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def isSystemTrayAvailable(self) -> bool:
        return True

    def showMessage(self, title: str, message: str, *_args) -> None:
        self.messages.append((title, message))


class FakeClipboard:
    def __init__(self) -> None:
        self.selected_text = ""

    def get_selected_text(self) -> str:
        return self.selected_text


class FakeTranslator:
    def __init__(self) -> None:
        self.available = True
        self.available_models = ["model-a"]
        self.stream_chunks = ["translated"]
        self.stream_error: Exception | None = None
        self.wait_until_cancel = False
        self.started = threading.Event()
        self.requests: list[dict[str, object]] = []
        self.updated_settings: list[AppSettings] = []
        self.cancel_count = 0

    def is_available(self) -> bool:
        return self.available

    def get_available_models(self) -> list[str]:
        return self.available_models

    def translate_stream(
        self,
        text: str,
        target_language: str | None = None,
        source_language: str | None = None,
        on_chunk=None,
        cancel_check=None,
    ):
        self.started.set()
        self.requests.append(
            {
                "text": text,
                "target_language": target_language,
                "source_language": source_language,
            }
        )

        if self.stream_error:
            raise self.stream_error

        if self.wait_until_cancel:
            while not (cancel_check and cancel_check()):
                time.sleep(0.01)
            return

        for chunk in self.stream_chunks:
            if cancel_check and cancel_check():
                return
            yield chunk

    def cancel(self) -> None:
        self.cancel_count += 1

    def update_settings(self, settings: AppSettings) -> None:
        self.updated_settings.append(settings)


class FakeOCRService:
    def __init__(self) -> None:
        self.capture_result: Path | None = Path("/tmp/lingoflow-test-capture.png")
        self.capture_error: ScreenCaptureError | None = None
        self.extract_result = OCRResult(text="OCR text", success=True)
        self.capture_calls = 0
        self.extract_paths: list[Path] = []
        self.cleanup_paths: list[Path] = []
        self.updated_settings: list[AppSettings] = []

    def capture_interactive(self) -> Path | None:
        self.capture_calls += 1
        if self.capture_error:
            raise self.capture_error
        return self.capture_result

    def extract_text(self, image_path: Path) -> OCRResult:
        self.extract_paths.append(image_path)
        return self.extract_result

    def cleanup_capture(self, image_path: Path) -> bool:
        self.cleanup_paths.append(image_path)
        return True

    def update_settings(self, settings: AppSettings) -> None:
        self.updated_settings.append(settings)


class FakeHotkeyManager:
    def __init__(self) -> None:
        self.registrations: list[tuple[object, str, object]] = []
        self.updated_settings: list[AppSettings] = []
        self.running = False

    def register(self, action, hotkey: str, callback, description: str = "") -> None:
        self.registrations.append((action, hotkey, callback))

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def is_running(self) -> bool:
        return self.running

    def update_settings(self, settings: AppSettings) -> None:
        self.updated_settings.append(settings)


class FakePopup:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.language_changed = FakeSignal()
        self.closed = FakeSignal()
        self.target_language = settings.translation.target_language
        self.shown: list[dict[str, object]] = []
        self.chunks: list[str] = []
        self.errors: list[str] = []
        self.cleared_count = 0
        self.started_count = 0
        self.finished_count = 0
        self.dismissed = False
        self.updated_settings: list[AppSettings] = []

    def show_with_text(
        self,
        source_text: str,
        target_language: str | None = None,
        source_language: str | None = None,
    ) -> None:
        if target_language:
            self.target_language = target_language
        self.shown.append(
            {
                "source_text": source_text,
                "target_language": target_language,
                "source_language": source_language,
            }
        )

    def append_translation(self, chunk: str) -> None:
        self.chunks.append(chunk)

    def start_translation(self) -> None:
        self.started_count += 1

    def finish_translation(self) -> None:
        self.finished_count += 1

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def clear_translation(self) -> None:
        self.cleared_count += 1
        self.chunks.clear()

    def get_target_language(self) -> str:
        return self.target_language

    def get_source_text(self) -> str:
        if not self.shown:
            return ""
        return str(self.shown[-1]["source_text"])

    def update_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.target_language = settings.translation.target_language
        self.updated_settings.append(settings)

    def dismiss(self) -> None:
        if self.dismissed:
            return
        self.dismissed = True
        self.closed.emit()


@dataclass
class ControllerHarness:
    controller: MainController
    settings: AppSettings
    clipboard: FakeClipboard
    translator: FakeTranslator
    ocr: FakeOCRService
    hotkeys: FakeHotkeyManager
    popups: list[FakePopup] = field(default_factory=list)

    @property
    def popup(self) -> FakePopup | None:
        return self.popups[-1] if self.popups else None


class UnsupportedPermissions:
    @staticmethod
    def is_supported() -> bool:
        return False


@pytest.fixture
def controller_harness(monkeypatch, qapp, isolated_settings_paths) -> ControllerHarness:
    settings = AppSettings()
    clipboard = FakeClipboard()
    translator = FakeTranslator()
    ocr = FakeOCRService()
    hotkeys = FakeHotkeyManager()
    popups: list[FakePopup] = []

    monkeypatch.setattr(
        main_window.AppSettings,
        "load",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(main_window, "TranslationService", lambda _settings: translator)
    monkeypatch.setattr(main_window, "OCRService", lambda _settings: ocr)
    monkeypatch.setattr(main_window, "ClipboardManager", lambda: clipboard)
    monkeypatch.setattr(main_window, "HotkeyManager", lambda _settings: hotkeys)
    monkeypatch.setattr(main_window, "MacOSPermissionService", UnsupportedPermissions)
    monkeypatch.setattr(tray_controller, "QSystemTrayIcon", FakeTrayIcon)

    def make_popup(popup_settings: AppSettings) -> FakePopup:
        popup = FakePopup(popup_settings)
        popups.append(popup)
        return popup

    monkeypatch.setattr(main_window, "TranslationPopup", make_popup)

    controller = MainController()
    harness = ControllerHarness(
        controller=controller,
        settings=settings,
        clipboard=clipboard,
        translator=translator,
        ocr=ocr,
        hotkeys=hotkeys,
        popups=popups,
    )

    yield harness

    controller._task_runner.cancel_all()
    for task in (controller._active_translation_task, controller._active_ocr_task):
        if task and task._thread:
            task._thread.join(timeout=1.0)
    if controller.tray_icon:
        controller.tray_icon.hide()
    controller.deleteLater()


def wait_for_idle_translation(qtbot, harness: ControllerHarness) -> None:
    qtbot.waitUntil(
        lambda: harness.popup is not None and harness.popup.finished_count == 1,
        timeout=2000,
    )
    qtbot.waitUntil(lambda: not harness.controller._is_translating, timeout=2000)


def test_translate_selection_shows_popup_and_streams_translation(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.clipboard.selected_text = "  Hello paper  "
    harness.translator.stream_chunks = ["你好", "论文"]

    harness.controller._on_translate_requested()
    wait_for_idle_translation(qtbot, harness)

    assert harness.popup is not None
    assert harness.popup.shown[-1] == {
        "source_text": "Hello paper",
        "target_language": None,
        "source_language": harness.settings.translation.source_language,
    }
    assert harness.popup.started_count == 1
    assert harness.popup.chunks == ["你好", "论文"]
    assert harness.translator.requests[-1]["text"] == "Hello paper"
    assert (
        harness.translator.requests[-1]["target_language"]
        == harness.settings.translation.target_language
    )
    assert "Ready" in harness.controller.tray_icon.tooltip


def test_translate_request_without_ollama_notifies_and_does_not_create_popup(
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.translator.available = False
    harness.clipboard.selected_text = "Hello"

    harness.controller._on_translate_requested()

    assert harness.popup is None
    assert harness.controller.tray_icon.messages[-1][0] == messages.OLLAMA_NOT_RUNNING_TITLE
    assert messages.OLLAMA_OFFLINE_STATUS in harness.controller.tray_icon.tooltip


def test_translate_request_without_selected_text_notifies(
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.clipboard.selected_text = "   "

    harness.controller._on_translate_requested()

    assert harness.popup is None
    assert harness.controller.tray_icon.messages[-1] == (
        messages.NO_TEXT_SELECTED_TITLE,
        messages.NO_TEXT_SELECTED_MESSAGE,
    )


def test_translate_request_truncates_very_long_selection(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.clipboard.selected_text = "a" * 5100

    harness.controller._on_translate_requested()
    wait_for_idle_translation(qtbot, harness)

    shown_text = harness.popup.shown[-1]["source_text"]
    assert len(shown_text) == 5003
    assert str(shown_text).endswith("...")
    assert harness.translator.requests[-1]["text"] == shown_text


def test_ocr_success_extracts_text_then_translates(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.ocr.extract_result = OCRResult(text="  OCR paper text  ", success=True)
    harness.translator.stream_chunks = ["OCR translation"]

    harness.controller._on_ocr_requested()
    wait_for_idle_translation(qtbot, harness)

    assert harness.ocr.capture_calls == 1
    assert harness.ocr.extract_paths == [harness.ocr.capture_result]
    assert harness.ocr.cleanup_paths == [harness.ocr.capture_result]
    assert harness.popup is not None
    assert harness.popup.shown[-1]["source_text"] == "OCR paper text"
    assert harness.translator.requests[-1]["text"] == "OCR paper text"


def test_ocr_cancelled_restores_ready_without_popup(
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.ocr.capture_result = None

    harness.controller._on_ocr_requested()

    assert harness.controller._is_processing_ocr is False
    assert harness.popup is None
    assert "Ready" in harness.controller.tray_icon.tooltip


def test_ocr_capture_error_notifies_without_starting_worker(
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.ocr.capture_error = ScreenCaptureError("screen permission missing")

    harness.controller._on_ocr_requested()

    assert harness.popup is None
    assert harness.controller._active_ocr_task is None
    assert harness.controller.tray_icon.messages[-1] == (
        messages.OCR_ERROR_TITLE,
        "screen permission missing",
    )


def test_ocr_empty_result_notifies_and_does_not_translate(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.ocr.extract_result = OCRResult(text="   ", success=True)

    harness.controller._on_ocr_requested()
    qtbot.waitUntil(lambda: not harness.controller._is_processing_ocr, timeout=2000)

    assert harness.popup is None
    assert harness.translator.requests == []
    assert harness.controller.tray_icon.messages[-1][0] == messages.NO_TEXT_FOUND_TITLE


def test_translation_error_is_shown_in_popup(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.clipboard.selected_text = "Hello"
    harness.translator.stream_error = OllamaError("model failed")

    harness.controller._on_translate_requested()
    qtbot.waitUntil(
        lambda: harness.popup is not None and bool(harness.popup.errors),
        timeout=2000,
    )
    qtbot.waitUntil(lambda: not harness.controller._is_translating, timeout=2000)

    assert harness.popup.errors == ["model failed"]
    assert "Ready" in harness.controller.tray_icon.tooltip


def test_popup_close_cancels_active_translation(
    qtbot,
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.clipboard.selected_text = "Slow text"
    harness.translator.wait_until_cancel = True

    harness.controller._on_translate_requested()
    assert harness.translator.started.wait(timeout=2.0)
    assert harness.popup is not None

    harness.popup.dismiss()

    qtbot.waitUntil(lambda: not harness.controller._is_translating, timeout=2000)
    assert harness.translator.cancel_count == 1
    assert harness.controller._active_translation_task is None
    assert harness.controller.popup is None


def test_settings_changed_updates_services_hotkeys_and_popup(
    controller_harness: ControllerHarness,
) -> None:
    harness = controller_harness
    harness.controller._ensure_popup()
    new_settings = harness.settings.model_copy(deep=True)
    new_settings.translation.target_language = "Japanese"

    harness.controller._on_settings_changed(new_settings)

    applied_settings = harness.controller.settings
    assert applied_settings is not new_settings
    assert applied_settings == new_settings
    assert harness.translator.updated_settings == [applied_settings]
    assert harness.ocr.updated_settings == [applied_settings]
    assert harness.hotkeys.updated_settings == [applied_settings]
    assert harness.popup is not None
    assert harness.popup.updated_settings == [applied_settings]
    assert harness.popup.target_language == "Japanese"


def test_stale_translation_signals_are_ignored(controller_harness: ControllerHarness) -> None:
    harness = controller_harness
    harness.controller._ensure_popup()

    harness.controller._on_translation_chunk(999, "stale")
    harness.controller._on_translation_error(999, "stale error")
    harness.controller._on_translation_completed(999)

    assert harness.popup is not None
    assert harness.popup.chunks == []
    assert harness.popup.errors == []
    assert harness.popup.finished_count == 0
