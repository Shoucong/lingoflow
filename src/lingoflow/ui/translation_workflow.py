"""Selected-text translation workflow coordination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from lingoflow.config.settings import AppSettings
from lingoflow.core.app_state import AppState, AppStateTracker
from lingoflow.core.ports import ClipboardPort, LLMProvider, Notifier
from lingoflow.core.session import SessionStatus, TranslationSession
from lingoflow.infrastructure.ollama_client import OllamaConnectionError, OllamaError
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui import messages
from lingoflow.ui.popup import TranslationPopup
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class TranslationSignals(Protocol):
    """Signals emitted by translation workers."""

    selection_ready: object
    translation_chunk: object
    translation_cleared: object
    translation_error: object
    translation_completed: object
    translation_finished: object


class TranslationWorkflow:
    """Coordinate selected-text translation, popup updates, and cancellation."""

    def __init__(
        self,
        settings: AppSettings,
        translator: LLMProvider,
        clipboard: ClipboardPort,
        task_runner: TaskRunner,
        app_state: AppStateTracker,
        signals: TranslationSignals,
        notifier: Notifier,
        popup_factory: Callable[[AppSettings], TranslationPopup],
    ) -> None:
        self.settings = settings
        self.translator = translator
        self.clipboard = clipboard
        self._task_runner = task_runner
        self._app_state = app_state
        self._signals = signals
        self._notifier = notifier
        self._popup_factory = popup_factory

        self.popup: TranslationPopup | None = None
        self.active_task: BackgroundTask | None = None
        self.session: TranslationSession | None = None

    @property
    def is_translating(self) -> bool:
        """Return whether a translation task is active."""
        return self._app_state.is_translating

    def apply_settings(self, settings: AppSettings) -> None:
        """Apply settings to workflow-owned UI."""
        if self.active_task:
            self.stop_from_popup()
        self.settings = settings
        if self.popup:
            self.popup.update_settings(settings)

    def translate_selection(self) -> None:
        """Capture and check the local service without blocking the Qt thread."""
        self.cancel_active("New selection requested", update_status=False)
        task = self._task_runner.create("selection")
        self.active_task = task
        self.session = TranslationSession(task.task_id)
        self._app_state.set(AppState.ACQUIRING)
        self._notifier.update_status("Reading selection...")
        task.start(self._selection_worker)

    def _selection_worker(self, task: BackgroundTask) -> None:
        text, error = "", ""
        try:
            if task.is_cancelled():
                return
            text = (self.clipboard.get_selected_text(cancel_check=task.is_cancelled) or "").strip()
            if not text:
                error = "empty"
            elif not task.is_cancelled() and not self.translator.is_available():
                error = "offline"
        except Exception:
            logger.exception("Could not capture selected text")
            error = "capture"
        if not task.is_cancelled():
            self._signals.selection_ready.emit(task.task_id, text, error)

    def on_selection_ready(self, task_id: int, text: str, error: str) -> None:
        if not self.is_active_task(task_id):
            return
        self.active_task = None
        self._app_state.reset()
        if error:
            if self.session:
                self.session.finish(SessionStatus.FAILED, error)
            if error == "offline":
                self._notifier.show_notification(
                    messages.OLLAMA_NOT_RUNNING_TITLE,
                    messages.OLLAMA_START_COMMAND,
                )
                self._notifier.update_status(messages.OLLAMA_OFFLINE_STATUS)
            elif error == "empty":
                self._notifier.show_notification(
                    messages.NO_TEXT_SELECTED_TITLE,
                    messages.NO_TEXT_SELECTED_MESSAGE,
                )
                self._notifier.update_status("Ready")
            else:
                self._notifier.show_notification(
                    "Selection unavailable",
                    "Could not read the selection. Check Accessibility permissions.",
                )
                self._notifier.update_status("Ready")
            return
        self.translate_text(text)

    def translate_text(self, text: str) -> None:
        """Show source text and start translating it."""
        self.cancel_active("New text requested", update_status=False)
        self.ensure_popup()
        self.popup.show_with_text(
            text,
            source_language=self.settings.translation.source_language,
        )
        self.start_translation(text)

    def start_translation(self, text: str) -> None:
        """Start translation in a background task."""
        if not self.popup:
            return

        self._app_state.set(AppState.TRANSLATING)
        self._notifier.update_status("Translating...")

        self.popup.start_translation()
        target_lang = self.popup.get_target_language()

        task = self._task_runner.create("translation")
        self.active_task = task
        self.session = TranslationSession(
            task.task_id,
            text,
            target_lang,
            SessionStatus.TRANSLATING,
        )
        task.start(lambda current_task: self._translate_worker(current_task, text, target_lang))

    def _translate_worker(
        self,
        task: BackgroundTask,
        text: str,
        target_language: str,
    ) -> None:
        """Background worker for translation."""
        max_retries = 2
        retry_count = 0
        emitted_text = False

        try:
            while retry_count <= max_retries:
                if task.is_cancelled():
                    logger.info("Translation cancelled")
                    return

                try:
                    for chunk in self.translator.translate_stream(
                        text,
                        target_language=target_language,
                        cancel_check=task.is_cancelled,
                    ):
                        if task.is_cancelled():
                            logger.info("Translation cancelled")
                            return
                        emitted_text = emitted_text or bool(chunk)
                        self._signals.translation_chunk.emit(task.task_id, chunk)

                    if task.is_cancelled():
                        logger.info("Translation cancelled")
                        return
                    self._signals.translation_completed.emit(task.task_id)

                    logger.info("Translation completed")
                    break

                except OllamaConnectionError as e:
                    if task.is_cancelled():
                        logger.info("Translation cancelled")
                        return

                    if emitted_text:
                        raise OllamaError(
                            "Connection interrupted. Partial output retained; retry when ready."
                        ) from e
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(
                            f"Connection failed, retrying ({retry_count}/{max_retries})..."
                        )
                        if task.cancel_event.wait(timeout=1.0):
                            logger.info("Translation cancelled")
                            return
                        self._signals.translation_cleared.emit(task.task_id)
                    else:
                        logger.error(f"Ollama connection error after {max_retries} retries: {e}")
                        self._signals.translation_error.emit(
                            task.task_id,
                            messages.OLLAMA_CONNECT_TRANSLATION_ERROR,
                        )

        except OllamaError as e:
            if task.is_cancelled():
                logger.info("Translation cancelled")
                return

            logger.error(f"Ollama error: {e}")
            self._signals.translation_error.emit(task.task_id, str(e))

        except Exception as e:
            if task.is_cancelled():
                logger.info("Translation cancelled")
                return

            logger.error(f"Translation error: {e}")
            self._signals.translation_error.emit(task.task_id, f"Translation failed: {e}")

        finally:
            if not task.is_cancelled():
                self._signals.translation_finished.emit(task.task_id)

    def on_finished(self, task_id: int) -> None:
        if not self.is_active_task(task_id):
            return
        self.active_task = None
        if self.session and self.session.status == SessionStatus.FAILED:
            self._app_state.mark_error("Failed")
            self._notifier.update_status("Failed")
        else:
            self._app_state.reset()
            self._notifier.update_status("Ready")

    def on_chunk(self, task_id: int, chunk: str) -> None:
        """Append a chunk to the active popup."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        if self.session and self.session.append(task_id, chunk):
            self.popup.append_translation(chunk)

    def on_cleared(self, task_id: int) -> None:
        """Clear active popup translation output."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        if self.session:
            self.session.translated_text = ""
        self.popup.clear_translation()

    def on_error(self, task_id: int, message: str) -> None:
        """Show a translation error."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        if self.session:
            self.session.finish(SessionStatus.FAILED, message)
        self.popup.show_error(message)

    def on_completed(self, task_id: int) -> None:
        """Mark popup translation complete."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        if self.session:
            self.session.finish(SessionStatus.COMPLETED)
        self.popup.finish_translation()

    def ensure_popup(self) -> None:
        """Ensure popup window exists."""
        if self.popup is None:
            self.popup = self._popup_factory(self.settings)
            self.popup.language_changed.connect(self.on_popup_language_changed)
            self.popup.closed.connect(self.on_popup_closed)
            self.popup.stop_requested.connect(self.stop_from_popup)
            self.popup.retry_requested.connect(self.retry_from_popup)

    def dismiss_popup(self, reason: str) -> None:
        """Dismiss the popup even if macOS has hidden it."""
        if not self.popup:
            return

        logger.debug(reason)
        try:
            self.popup.dismiss()
        except RuntimeError:
            self.popup = None

    def is_active_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active translation."""
        return (
            self.active_task is not None
            and self.active_task.task_id == task_id
            and not self.active_task.is_cancelled()
        )

    def cancel_active(self, reason: str, update_status: bool = True) -> None:
        """Cancel the active translation task if one is running."""
        if self.active_task is None:
            return

        logger.info(reason)
        self._app_state.set(AppState.CANCELLING)
        if self.session:
            self.session.finish(SessionStatus.CANCELLED)
        self._task_runner.cancel(self.active_task)
        self.translator.cancel()
        self._app_state.reset()
        self.active_task = None

        if update_status:
            self._notifier.update_status("Ready")

    def stop_from_popup(self) -> None:
        self.cancel_active("Stopped by user")
        if self.popup:
            self.popup.stop_translation()

    def retry_from_popup(self, text: str) -> None:
        if not text.strip():
            return
        self.cancel_active("Retry requested", update_status=False)
        if self.popup:
            self.popup.clear_translation()
            self.start_translation(text)

    def on_popup_closed(self) -> None:
        """Cancel translation work when the popup is dismissed."""
        self.cancel_active(messages.POPUP_CLOSED_CANCEL_TRANSLATION_REASON)
        self.popup = None
        self.session = None

    def on_popup_language_changed(self, language: str) -> None:
        """Re-translate when user changes target language in popup."""
        self.cancel_active(
            messages.TARGET_LANGUAGE_CHANGED_CANCEL_REASON,
            update_status=False,
        )

        if not self.popup:
            return

        source_text = self.popup.get_source_text()
        if source_text:
            self.popup.clear_translation()
            self.start_translation(source_text)

    def shutdown(self) -> None:
        """Cancel active translation during app shutdown."""
        self.cancel_active(messages.QUIT_CANCEL_TRANSLATION_REASON, update_status=False)
