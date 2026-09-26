"""
Main window and system tray controller for LingoFlow.

This is the central hub that connects:
- Hotkey manager (input triggers)
- Translation service (processing)
- Popup window (output display)
- Settings dialog (configuration)
"""

import platform
import shlex
import sys

from PyQt6.QtCore import QObject, QProcess, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from lingoflow.config.constants import APP_NAME, APP_VERSION
from lingoflow.config.settings import AppSettings
from lingoflow.core.app_state import AppState, AppStateTracker
from lingoflow.core.models import HotkeyAction, OCRResult
from lingoflow.core.ports import ClipboardPort, HotkeyBackend, LLMProvider, OCRBackend
from lingoflow.infrastructure.macos.clipboard import ClipboardManager
from lingoflow.infrastructure.macos.hotkeys import HotkeyManager
from lingoflow.infrastructure.macos.ocr import OCRService
from lingoflow.infrastructure.macos.permissions import MacOSPermissionService
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.infrastructure.translation_service import create_translation_service
from lingoflow.ui import messages
from lingoflow.ui.menu_windows import AboutWindow, MenuWindowPresenter, activate_application
from lingoflow.ui.ocr_workflow import OCRWorkflow
from lingoflow.ui.onboarding_dialog import OnboardingDialog
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.settings_coordinator import SettingsCoordinator
from lingoflow.ui.settings_dialog import SettingsDialog
from lingoflow.ui.translation_workflow import TranslationWorkflow
from lingoflow.ui.tray_controller import TrayController, format_hotkey
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Signal Bridge for Cross-Thread Communication
# =============================================================================


class MainSignals(QObject):
    """Signals for thread-safe communication from hotkey callbacks."""

    translate_requested = pyqtSignal()
    ocr_requested = pyqtSignal()
    show_error = pyqtSignal(str, str)  # title, message
    status_update = pyqtSignal(str)  # status text
    selection_ready = pyqtSignal(int, str, str)
    startup_checked = pyqtSignal(int, object)
    translation_checkpoint = pyqtSignal(int, object)
    translation_chunk = pyqtSignal(int, str)  # task id, text chunk
    translation_cleared = pyqtSignal(int)  # task id
    translation_error = pyqtSignal(int, str)  # task id, message
    translation_completed = pyqtSignal(int)  # task id
    translation_finished = pyqtSignal(int)  # translation task id
    translation_source_detected = pyqtSignal(int, str)  # task id, source language
    ocr_recognizing = pyqtSignal(int)
    ocr_finished = pyqtSignal(int, object)  # task id, OCRResult


# =============================================================================
# Main Controller
# =============================================================================


class MainController(QObject):
    """
    Main application controller.

    Manages:
    - System tray icon and menu
    - Global hotkey handling
    - Translation workflow
    - OCR workflow
    - Settings management

    This class coordinates all the pieces but doesn't create a visible window.
    The app lives in the system tray.
    """

    def __init__(self):
        super().__init__()

        self.settings = AppSettings.load()
        self.signals = MainSignals()

        # Core services
        self.translator: LLMProvider = create_translation_service(self.settings)
        self.ocr_service: OCRBackend = OCRService(self.settings)
        self.clipboard: ClipboardPort = ClipboardManager()
        self.hotkey_manager: HotkeyBackend = HotkeyManager(self.settings)
        self.permission_service = (
            MacOSPermissionService() if MacOSPermissionService.is_supported() else None
        )

        # UI components
        self.tray_controller: TrayController | None = None
        self._onboarding_dialog: OnboardingDialog | None = None
        self._about_window: AboutWindow | None = None
        self.menu_windows = MenuWindowPresenter(self._activate_app_for_dialog)

        # State
        self._app_state = AppStateTracker()
        self._task_runner = TaskRunner()
        self._quitting = False
        self._startup_task_id = None
        self._setup_tray()
        self.translation_workflow = TranslationWorkflow(
            settings=self.settings,
            translator=self.translator,
            clipboard=self.clipboard,
            task_runner=self._task_runner,
            app_state=self._app_state,
            signals=self.signals,
            notifier=self.tray_controller,
            popup_factory=lambda settings: TranslationPopup(settings),
            on_settings_requested=self._show_settings,
        )
        self.ocr_workflow = OCRWorkflow(
            settings=self.settings,
            ocr_service=self.ocr_service,
            task_runner=self._task_runner,
            app_state=self._app_state,
            signals=self.signals,
            notifier=self.tray_controller,
            translation_workflow=self.translation_workflow,
        )
        self.settings_coordinator = SettingsCoordinator(
            settings=self.settings,
            on_settings_changed=self._on_settings_changed,
            present=self._raise_dialog,
        )
        self._setup_signals()
        self._setup_hotkeys()

        logger.info(f"{APP_NAME} v{APP_VERSION} initialized")

    @property
    def app_state(self) -> AppState:
        """Return the current high-level app state."""
        return self._app_state.current

    @property
    def tray_icon(self):
        """Return the underlying tray icon for compatibility/tests."""
        return self.tray_controller.tray_icon if self.tray_controller else None

    @property
    def popup(self):
        """Return the active translation popup."""
        return self.translation_workflow.popup

    @property
    def _active_translation_task(self) -> BackgroundTask | None:
        """Return the active translation task for compatibility/tests."""
        return self.translation_workflow.active_task

    @property
    def _active_ocr_task(self) -> BackgroundTask | None:
        """Return the active OCR task for compatibility/tests."""
        return self.ocr_workflow.active_task

    @property
    def _settings_dialog(self):
        """Return active settings dialog for compatibility/tests."""
        return self.settings_coordinator.dialog

    @property
    def _settings_dialog_open(self) -> bool:
        """Return whether the settings dialog is open."""
        return self.settings_coordinator.is_open

    @property
    def _is_translating(self) -> bool:
        """Compatibility wrapper while workflows move to AppState."""
        return self._app_state.is_translating

    @_is_translating.setter
    def _is_translating(self, value: bool) -> None:
        if value:
            self._app_state.set(AppState.TRANSLATING)
        elif self._app_state.current in {AppState.TRANSLATING, AppState.CANCELLING}:
            self._app_state.reset()

    @property
    def _is_processing_ocr(self) -> bool:
        """Compatibility wrapper while workflows move to AppState."""
        return self._app_state.is_ocr_active

    @_is_processing_ocr.setter
    def _is_processing_ocr(self, value: bool) -> None:
        if value:
            self._app_state.set(AppState.OCR_RECOGNIZING)
        elif self._app_state.is_ocr_active:
            self._app_state.reset()

    def _set_app_state(self, state: AppState, detail: str | None = None) -> None:
        """Set high-level state explicitly for non-boolean workflow steps."""
        self._app_state.set(state, detail=detail)

    # -------------------------------------------------------------------------
    # Setup Methods
    # -------------------------------------------------------------------------

    def _setup_signals(self) -> None:
        """Connect cross-thread signals."""
        self.signals.translate_requested.connect(self._on_translate_requested)
        self.signals.selection_ready.connect(self.translation_workflow.on_selection_ready)
        self.signals.startup_checked.connect(self._on_startup_checked)
        self.signals.ocr_requested.connect(self._on_ocr_requested)
        self.signals.show_error.connect(self._show_error_dialog)
        self.signals.status_update.connect(self._update_status)
        self.signals.translation_chunk.connect(self._on_translation_chunk)
        self.signals.translation_checkpoint.connect(self.translation_workflow.on_checkpoint)
        self.signals.translation_cleared.connect(self._on_translation_cleared)
        self.signals.translation_error.connect(self._on_translation_error)
        self.signals.translation_completed.connect(self._on_translation_completed)
        self.signals.translation_finished.connect(self._on_translation_finished)
        self.signals.translation_source_detected.connect(
            self.translation_workflow.on_source_detected
        )
        self.signals.ocr_finished.connect(self._on_ocr_finished)
        self.signals.ocr_recognizing.connect(self.ocr_workflow.on_recognizing)

    def _setup_tray(self) -> None:
        """Set up the system tray icon and menu."""
        self.tray_controller = TrayController(
            settings=self.settings,
            on_translate=self._on_translate_requested,
            on_ocr=self._on_ocr_requested,
            on_input=self._open_input,
            on_settings=self._show_settings,
            on_permissions=(
                (lambda: self._show_onboarding(force=True)) if self.permission_service else None
            ),
            on_about=self._show_about,
            on_quit=self._quit,
        )

    def _setup_hotkeys(self) -> None:
        """Register global hotkeys."""
        # Register translate hotkey
        self.hotkey_manager.register(
            HotkeyAction.TRANSLATE,
            self.settings.hotkeys.translate,
            self._on_hotkey_translate,
            description="Translate selected text",
        )

        # Register OCR hotkey
        self.hotkey_manager.register(
            HotkeyAction.OCR,
            self.settings.hotkeys.ocr,
            self._on_hotkey_ocr,
            description="OCR screenshot and translate",
        )

    def _start_hotkeys(self) -> None:
        """Start listening for registered hotkeys."""
        self.hotkey_manager.start()
        if self.hotkey_manager.is_running():
            logger.info("Hotkeys registered and listening")
        else:
            logger.error("Native hotkey listener did not start")
            self._show_notification(
                messages.HOTKEYS_UNAVAILABLE_TITLE,
                messages.HOTKEYS_PERMISSION_RESTART,
            )

    def _format_hotkey(self, action: str) -> str:
        """Format hotkey for display in menu."""
        return format_hotkey(self.settings, action)

    # -------------------------------------------------------------------------
    # Hotkey Callbacks (Called from Background Thread)
    # -------------------------------------------------------------------------

    def _on_hotkey_translate(self) -> None:
        """Called when translate hotkey is pressed (from background thread)."""
        logger.debug("Translate hotkey triggered")
        # Emit signal to handle on main thread
        self.signals.translate_requested.emit()

    def _on_hotkey_ocr(self) -> None:
        """Called when OCR hotkey is pressed (from background thread)."""
        logger.debug("OCR hotkey triggered")
        # Emit signal to handle on main thread
        self.signals.ocr_requested.emit()

    # -------------------------------------------------------------------------
    # Main Thread Handlers
    # -------------------------------------------------------------------------

    def _on_translate_requested(self) -> None:
        """Handle translation request (main thread)."""
        self.ocr_workflow.cancel_active()
        self.translation_workflow.translate_selection()

    def _on_ocr_requested(self) -> None:
        """Handle OCR request (main thread)."""
        self.translation_workflow.cancel_active("New OCR requested")
        # A pinned reading window stays and receives the recognized text.
        self.translation_workflow.dismiss_popup("Starting screenshot capture", keep_pinned=True)
        self.ocr_workflow.request_ocr()

    def _open_input(self) -> None:
        """Open an editable source without requiring a selection or screenshot."""
        self.ocr_workflow.cancel_active()
        self.translation_workflow.review_text("")

    def _ocr_worker(self, task: BackgroundTask, image_path) -> None:
        """Background worker for OCR text extraction."""
        self.ocr_workflow._ocr_worker(task, image_path)

    def _on_ocr_finished(self, task_id: int, result: OCRResult) -> None:
        """Handle OCR completion (main thread)."""
        self.ocr_workflow.on_finished(task_id, result)

    def _on_translation_finished(self, task_id: int) -> None:
        """Handle translation completion (main thread)."""
        self.translation_workflow.on_finished(task_id)

    def _on_translation_chunk(self, task_id: int, chunk: str) -> None:
        """Append a translation chunk for the active task."""
        self.translation_workflow.on_chunk(task_id, chunk)

    def _on_translation_cleared(self, task_id: int) -> None:
        """Clear translation output for the active task."""
        self.translation_workflow.on_cleared(task_id)

    def _on_translation_error(self, task_id: int, message: str) -> None:
        """Show a translation error for the active task."""
        self.translation_workflow.on_error(task_id, message)

    def _on_translation_completed(self, task_id: int) -> None:
        """Mark popup translation complete for the active task."""
        self.translation_workflow.on_completed(task_id)

    # -------------------------------------------------------------------------
    # Translation Logic
    # -------------------------------------------------------------------------

    def _start_translation(self, text: str) -> None:
        """Start translation in a background thread."""
        self.translation_workflow.start_translation(text)

    def _translate_worker(
        self,
        task: BackgroundTask,
        text: str,
        target_language: str,
    ) -> None:
        """Background worker for translation."""
        self.translation_workflow._translate_worker(task, text, target_language)

    # -------------------------------------------------------------------------
    # UI Helpers
    # -------------------------------------------------------------------------

    def _ensure_popup(self) -> None:
        """Ensure popup window exists."""
        self.translation_workflow.ensure_popup()

    def _dismiss_popup(self, reason: str) -> None:
        """Dismiss the popup even if macOS has hidden it outside Qt visibility state."""
        self.translation_workflow.dismiss_popup(reason)

    def _is_active_translation_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active translation."""
        return self.translation_workflow.is_active_task(task_id)

    def _is_active_ocr_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active OCR operation."""
        return self.ocr_workflow.is_active_task(task_id)

    def _cancel_active_translation(self, reason: str, update_status: bool = True) -> None:
        """Cancel the active translation task if one is running."""
        self.translation_workflow.cancel_active(reason, update_status=update_status)

    def _on_popup_closed(self) -> None:
        """Cancel translation work when the popup is dismissed."""
        self.translation_workflow.on_popup_closed()

    def _on_popup_language_changed(self, language: str) -> None:
        """Re-translate when user changes target language in popup."""
        self.translation_workflow.on_popup_language_changed(language)

    def _update_status(self, status: str) -> None:
        """Update tray icon status."""
        if self.tray_controller:
            self.tray_controller.update_status(status)

    def _show_notification(self, title: str, message: str) -> None:
        """Show a system notification."""
        if self.tray_controller:
            self.tray_controller.show_notification(title, message)

    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show an error dialog."""
        QMessageBox.critical(None, title, message)

    def handle_external_launch(self) -> None:
        """Handle a second launch while this instance is already running."""
        if self._onboarding_dialog:
            self._present_onboarding(self._onboarding_dialog)
            return

        if self._settings_dialog_open:
            self.settings_coordinator.raise_current()
            return

        self._activate_app_for_dialog()
        self._show_notification(
            messages.already_running_title(),
            messages.ALREADY_RUNNING_MESSAGE,
        )

    # -------------------------------------------------------------------------
    # Menu Actions
    # -------------------------------------------------------------------------

    def _show_settings(self, section: str | None = None) -> None:
        """Show the settings dialog, optionally at a section such as "speech"."""
        self.settings_coordinator.show(section or None)

    def _on_settings_closed(self, dialog: SettingsDialog) -> None:
        """Clear settings dialog state after a modeless settings window closes."""
        self.settings_coordinator.on_closed(dialog)

    def _activate_app_for_dialog(self) -> None:
        """Bring this tray app forward before showing a real dialog on macOS."""
        activate_application()

    def _raise_dialog(self, dialog) -> None:
        """Show and foreground a menu window with the shared presentation policy."""
        self.menu_windows.present(dialog)

    def _on_settings_changed(self, new_settings: AppSettings) -> None:
        """Handle settings changes."""
        settings_snapshot = new_settings.model_copy(deep=True)
        self.settings = settings_snapshot
        self.settings_coordinator.update_settings(settings_snapshot)

        # Update services
        self.translator.update_settings(settings_snapshot)
        self.ocr_service.update_settings(settings_snapshot)
        self.hotkey_manager.update_settings(settings_snapshot)
        if self.tray_controller:
            self.tray_controller.update_settings(settings_snapshot)

        self.translation_workflow.apply_settings(settings_snapshot)
        self.ocr_workflow.apply_settings(settings_snapshot)

        logger.info("Settings applied to all services")

    def _show_onboarding(self, force: bool = False) -> None:
        """Show first-run setup when needed."""
        if not self.permission_service:
            return

        if self._onboarding_dialog:
            self._present_onboarding(self._onboarding_dialog)
            return

        permissions_ready = self.permission_service.required_permissions_ready()
        if not force and self.settings.onboarding.completed and permissions_ready:
            return

        dialog = OnboardingDialog(self.permission_service)
        self._onboarding_dialog = dialog
        dialog.finished.connect(lambda _: self._on_onboarding_finished(dialog))
        dialog.restart_requested.connect(self._restart_app)
        self._present_onboarding(dialog)

    def _present_onboarding(self, dialog: OnboardingDialog) -> None:
        dialog.prepare_for_user()
        self.menu_windows.present(dialog)

    def _on_onboarding_finished(self, dialog: OnboardingDialog) -> None:
        """Persist first-run setup state after the setup window closes."""
        if dialog is not self._onboarding_dialog:
            return

        self._onboarding_dialog = None
        if dialog.completed_successfully:
            self.settings.onboarding.completed = True
            try:
                self.settings.save()
            except Exception as e:
                logger.warning(f"Could not save onboarding state: {e}")
            logger.info("Onboarding completed")
            if not self.hotkey_manager.is_running():
                self._start_hotkeys()

        dialog.deleteLater()

    def _show_about(self) -> None:
        """Show the reusable About window in front, with one click."""
        hotkeys = (self._format_hotkey("translate"), self._format_hotkey("ocr"))
        if self._about_window is None:
            self._about_window = AboutWindow(self.settings, hotkeys)
        else:
            self._about_window.update_content(self.settings, hotkeys)
        self.menu_windows.present(self._about_window)

    def _restart_app(self) -> None:
        """Best-effort restart after macOS privacy permission changes."""
        logger.info("Restarting application after permission setup")
        if platform.system() == "Darwin":
            try:
                from Foundation import NSBundle

                bundle_path = str(NSBundle.mainBundle().bundlePath())
                if bundle_path.endswith(".app"):
                    command = f"sleep 0.8; /usr/bin/open {shlex.quote(bundle_path)}"
                    QProcess.startDetached("/bin/sh", ["-c", command])
            except Exception as e:
                logger.warning(f"Could not schedule app relaunch: {e}")
        elif sys.argv:
            command = "sleep 0.8; " + " ".join(
                shlex.quote(arg) for arg in [sys.executable, *sys.argv]
            )
            QProcess.startDetached("/bin/sh", ["-c", command])

        self._quit()

    def _quit(self) -> None:
        """Quit the application."""
        logger.info("Quitting application")
        self._quitting = True

        # Stop any active translation
        self._cancel_active_translation(
            messages.QUIT_CANCEL_TRANSLATION_REASON,
            update_status=False,
        )
        self.ocr_workflow.shutdown()

        # Stop hotkey listener
        self.hotkey_manager.stop()

        # Hide tray icon
        if self.tray_controller:
            self.tray_controller.hide()

        if self._onboarding_dialog:
            self._onboarding_dialog.close()
            self._onboarding_dialog = None
        if self._about_window:
            self._about_window.close()

        self._task_runner.shutdown()

        # Quit application
        QApplication.quit()

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the application (called after QApplication.exec())."""
        self._show_onboarding()
        self._start_hotkeys()

        task = self._task_runner.create("startup-check")
        self._startup_task_id = task.task_id
        settings_key = (self.settings.ollama.host, self.settings.ollama.model)
        task.start(lambda task: self._startup_worker(task, settings_key))

    def _startup_worker(self, task: BackgroundTask, settings_key: tuple[str, str]) -> None:
        available = self.translator.is_available()
        models = self.translator.get_available_models() if available else []
        if not task.is_cancelled():
            self.signals.startup_checked.emit(task.task_id, (settings_key, available, models))

    def _on_startup_checked(self, task_id: int, result) -> None:
        settings_key, available, models = result
        if (
            self._quitting
            or task_id != self._startup_task_id
            or self._app_state.is_busy
            or settings_key != (self.settings.ollama.host, self.settings.ollama.model)
        ):
            return
        if not available:
            self._show_notification(
                messages.OLLAMA_NOT_RUNNING_TITLE,
                messages.OLLAMA_START_COMMAND_FOR_TRANSLATION,
            )
            self._update_status(messages.OLLAMA_OFFLINE_STATUS)
        elif self.settings.ollama.model not in models:
            self._show_notification(
                messages.MODEL_NOT_FOUND_TITLE,
                messages.MODEL_NOT_FOUND_MESSAGE,
            )
            self._update_status("Model unavailable")
        else:
            self._update_status("Ready")
