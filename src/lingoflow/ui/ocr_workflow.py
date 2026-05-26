"""OCR capture and recognition workflow coordination."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lingoflow.config.settings import AppSettings
from lingoflow.core.app_state import AppState, AppStateTracker
from lingoflow.core.ocr import OCRResult, ScreenCaptureError
from lingoflow.core.ports import Notifier, OCRBackend
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui import messages
from lingoflow.ui.translation_workflow import TranslationWorkflow
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class OCRSignals(Protocol):
    """Signals emitted by OCR workers."""

    ocr_finished: object


class OCRWorkflow:
    """Coordinate screen capture, OCR extraction, and translation handoff."""

    def __init__(
        self,
        settings: AppSettings,
        ocr_service: OCRBackend,
        task_runner: TaskRunner,
        app_state: AppStateTracker,
        signals: OCRSignals,
        notifier: Notifier,
        translation_workflow: TranslationWorkflow,
    ) -> None:
        self.settings = settings
        self.ocr_service = ocr_service
        self._task_runner = task_runner
        self._app_state = app_state
        self._signals = signals
        self._notifier = notifier
        self._translation_workflow = translation_workflow
        self.active_task: BackgroundTask | None = None

    @property
    def is_processing(self) -> bool:
        """Return whether OCR capture or recognition is active."""
        return self._app_state.is_ocr_active

    def apply_settings(self, settings: AppSettings) -> None:
        """Apply settings to the workflow."""
        self.settings = settings

    def request_ocr(self) -> None:
        """Capture a selected screen region and translate extracted text."""
        if self._app_state.is_translating or self._app_state.is_ocr_active:
            logger.debug("Translation or OCR already in progress, ignoring")
            return

        logger.info("Starting OCR capture")
        self._app_state.set(AppState.CAPTURING)
        self._notifier.update_status("Capturing...")

        try:
            image_path = self.ocr_service.capture_interactive()
        except ScreenCaptureError as e:
            logger.error(f"OCR capture failed: {e}")
            self._notifier.show_notification(messages.OCR_ERROR_TITLE, str(e))
            self._app_state.reset()
            self._notifier.update_status("Ready")
            return

        if image_path is None:
            logger.debug("OCR cancelled by user")
            self._app_state.reset()
            self._notifier.update_status("Ready")
            return

        self._app_state.set(AppState.OCR_RECOGNIZING)
        self._notifier.update_status("Recognizing...")

        self.active_task = self._task_runner.create("ocr")
        self.active_task.start(lambda task: self._ocr_worker(task, image_path))

    def _ocr_worker(self, task: BackgroundTask, image_path: Path) -> None:
        """Background worker for OCR text extraction."""
        result = OCRResult(text="", success=False, error_message="OCR cancelled")
        try:
            if task.is_cancelled():
                return
            result = self.ocr_service.extract_text(image_path)
        except Exception as e:
            logger.error(f"OCR worker failed: {e}")
            result = OCRResult(text="", success=False, error_message=str(e))
        finally:
            if self.ocr_service.cleanup_capture(image_path):
                result.source_image_path = None

        if not task.is_cancelled():
            self._signals.ocr_finished.emit(task.task_id, result)

    def on_finished(self, task_id: int, result: OCRResult) -> None:
        """Handle OCR completion on the main thread."""
        if not self.is_active_task(task_id):
            logger.debug(f"Ignoring stale OCR finish signal: {task_id}")
            return

        self._app_state.reset()
        self.active_task = None

        if not result.success:
            logger.error(f"OCR failed: {result.error_message}")
            self._notifier.show_notification(
                messages.OCR_ERROR_TITLE,
                result.error_message or messages.OCR_FAILED_MESSAGE,
            )
            self._notifier.update_status("Ready")
            return

        if not result.text or not result.text.strip():
            logger.debug("No text extracted from image")
            self._notifier.show_notification(
                messages.NO_TEXT_FOUND_TITLE,
                messages.NO_TEXT_FOUND_MESSAGE,
            )
            self._notifier.update_status("Ready")
            return

        extracted_text = result.text.strip()
        if self.settings.privacy.allow_content_logging:
            logger.info(f"OCR extracted text: {extracted_text[:80]}...")
        else:
            logger.info(f"OCR extracted text ({len(extracted_text)} chars)")

        self._translation_workflow.translate_text(extracted_text)

    def is_active_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active OCR operation."""
        return (
            self._app_state.is_ocr_active
            and self.active_task is not None
            and self.active_task.task_id == task_id
            and not self.active_task.is_cancelled()
        )

    def cancel_active(self) -> None:
        """Cancel active OCR work."""
        self._task_runner.cancel(self.active_task)
        self.active_task = None
        if self._app_state.is_ocr_active:
            self._app_state.reset()

    def shutdown(self) -> None:
        """Cancel OCR during app shutdown."""
        self.cancel_active()
