"""Selected-text translation workflow coordination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from lingoflow.config.settings import AppSettings
from lingoflow.core.app_state import AppState, AppStateTracker
from lingoflow.core.ports import ClipboardPort, LLMProvider, Notifier
from lingoflow.infrastructure.ollama_client import OllamaConnectionError, OllamaError
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui import messages
from lingoflow.ui.popup import TranslationPopup
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class TranslationSignals(Protocol):
    """Signals emitted by translation workers."""

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

    @property
    def is_translating(self) -> bool:
        """Return whether a translation task is active."""
        return self._app_state.is_translating

    def apply_settings(self, settings: AppSettings) -> None:
        """Apply settings to workflow-owned UI."""
        self.settings = settings
        if self.popup:
            self.popup.update_settings(settings)

    def translate_selection(self) -> None:
        """Translate the current selected text."""
        if self._app_state.is_translating or self._app_state.is_ocr_active:
            logger.debug("Translation or OCR already in progress, ignoring")
            return

        if not self.translator.is_available():
            self._notifier.show_notification(
                messages.OLLAMA_NOT_RUNNING_TITLE,
                messages.OLLAMA_START_COMMAND,
            )
            self._notifier.update_status(messages.OLLAMA_OFFLINE_STATUS)
            return

        selected_text = self.clipboard.get_selected_text()

        if not selected_text or not selected_text.strip():
            logger.debug("No text selected")
            self._notifier.show_notification(
                messages.NO_TEXT_SELECTED_TITLE,
                messages.NO_TEXT_SELECTED_MESSAGE,
            )
            return

        selected_text = selected_text.strip()

        max_length = 5000
        if len(selected_text) > max_length:
            logger.warning(f"Text too long ({len(selected_text)} chars), truncating")
            selected_text = selected_text[:max_length] + "..."

        if self.settings.privacy.allow_content_logging:
            logger.info(f"Translating selected text: {selected_text[:80]}...")
        else:
            logger.info(f"Translating selected text ({len(selected_text)} chars)")

        self.translate_text(selected_text)

    def translate_text(self, text: str) -> None:
        """Show source text and start translating it."""
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
        """Handle translation completion on the main thread."""
        if not self.is_active_task(task_id):
            logger.debug(f"Ignoring stale translation finish signal: {task_id}")
            return

        self._app_state.reset()
        self.active_task = None
        self._notifier.update_status("Ready")

    def on_chunk(self, task_id: int, chunk: str) -> None:
        """Append a chunk to the active popup."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        self.popup.append_translation(chunk)

    def on_cleared(self, task_id: int) -> None:
        """Clear active popup translation output."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        self.popup.clear_translation()

    def on_error(self, task_id: int, message: str) -> None:
        """Show a translation error."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        self.popup.show_error(message)

    def on_completed(self, task_id: int) -> None:
        """Mark popup translation complete."""
        if not self.is_active_task(task_id) or not self.popup:
            return
        self.popup.finish_translation()

    def ensure_popup(self) -> None:
        """Ensure popup window exists."""
        if self.popup is None:
            self.popup = self._popup_factory(self.settings)
            self.popup.language_changed.connect(self.on_popup_language_changed)
            self.popup.closed.connect(self.on_popup_closed)

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
            self._app_state.is_translating
            and self.active_task is not None
            and self.active_task.task_id == task_id
            and not self.active_task.is_cancelled()
        )

    def cancel_active(self, reason: str, update_status: bool = True) -> None:
        """Cancel the active translation task if one is running."""
        if not self._app_state.is_translating:
            return

        logger.info(reason)
        self._app_state.set(AppState.CANCELLING)
        self._task_runner.cancel(self.active_task)
        self.translator.cancel()
        self._app_state.reset()
        self.active_task = None

        if update_status:
            self._notifier.update_status("Ready")

    def on_popup_closed(self) -> None:
        """Cancel translation work when the popup is dismissed."""
        self.cancel_active(messages.POPUP_CLOSED_CANCEL_TRANSLATION_REASON)
        self.popup = None

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
