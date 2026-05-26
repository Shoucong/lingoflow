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
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QObject, QProcess, QTimer
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
)

from lingoflow.config.settings import AppSettings
from lingoflow.config.constants import APP_ICON_FILE, APP_NAME, APP_VERSION
from lingoflow.core.hotkey import HotkeyManager, HotkeyAction
from lingoflow.core.translator import TranslationService
from lingoflow.core.ocr import OCRService, OCRResult, ScreenCaptureError
from lingoflow.infrastructure.clipboard import ClipboardManager
from lingoflow.infrastructure.macos_permissions import MacOSPermissionService
from lingoflow.infrastructure.ollama_client import OllamaConnectionError, OllamaError
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui.onboarding_dialog import OnboardingDialog
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.settings_dialog import SettingsDialog
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
    translation_chunk = pyqtSignal(int, str)  # task id, text chunk
    translation_cleared = pyqtSignal(int)  # task id
    translation_error = pyqtSignal(int, str)  # task id, message
    translation_completed = pyqtSignal(int)  # task id
    translation_finished = pyqtSignal(int)  # translation task id
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
        self.translator = TranslationService(self.settings)
        self.ocr_service = OCRService(self.settings)
        self.clipboard = ClipboardManager()
        self.hotkey_manager = HotkeyManager(self.settings)
        self.permission_service = (
            MacOSPermissionService() if MacOSPermissionService.is_supported() else None
        )
        
        # UI components
        self.popup: Optional[TranslationPopup] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._settings_dialog: Optional[SettingsDialog] = None
        self._onboarding_dialog: Optional[OnboardingDialog] = None
        
        # State
        self._is_translating = False
        self._is_processing_ocr = False
        self._task_runner = TaskRunner()
        self._active_translation_task: Optional[BackgroundTask] = None
        self._active_ocr_task: Optional[BackgroundTask] = None
        self._settings_dialog_open = False
        
        self._setup_signals()
        self._setup_tray()
        self._setup_hotkeys()
        
        logger.info(f"{APP_NAME} v{APP_VERSION} initialized")

    # -------------------------------------------------------------------------
    # Setup Methods
    # -------------------------------------------------------------------------

    def _setup_signals(self) -> None:
        """Connect cross-thread signals."""
        self.signals.translate_requested.connect(self._on_translate_requested)
        self.signals.ocr_requested.connect(self._on_ocr_requested)
        self.signals.show_error.connect(self._show_error_dialog)
        self.signals.status_update.connect(self._update_status)
        self.signals.translation_chunk.connect(self._on_translation_chunk)
        self.signals.translation_cleared.connect(self._on_translation_cleared)
        self.signals.translation_error.connect(self._on_translation_error)
        self.signals.translation_completed.connect(self._on_translation_completed)
        self.signals.translation_finished.connect(self._on_translation_finished)
        self.signals.ocr_finished.connect(self._on_ocr_finished)

    def _setup_tray(self) -> None:
        """Set up the system tray icon and menu."""
        self.tray_icon = QSystemTrayIcon()
        
        icon = QIcon(str(APP_ICON_FILE))
        if icon.isNull():
            logger.warning(f"Could not load app icon: {APP_ICON_FILE}")
            icon = QApplication.style().standardIcon(
                QApplication.style().StandardPixmap.SP_ComputerIcon
            )
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip(f"{APP_NAME} - Ready")
        
        # Create menu
        menu = QMenu()
        
        # Status item (non-clickable)
        self.status_action = QAction("● Ready", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        
        menu.addSeparator()
        
        # Translate action
        translate_action = QAction(f"Translate Selection ({self._format_hotkey('translate')})", menu)
        translate_action.triggered.connect(self._on_translate_requested)
        menu.addAction(translate_action)
        
        # OCR action
        ocr_action = QAction(f"OCR Screenshot ({self._format_hotkey('ocr')})", menu)
        ocr_action.triggered.connect(self._on_ocr_requested)
        menu.addAction(ocr_action)
        
        menu.addSeparator()
        
        # Settings
        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        if self.permission_service:
            permissions_action = QAction("Setup Permissions...", menu)
            permissions_action.triggered.connect(lambda: self._show_onboarding(force=True))
            menu.addAction(permissions_action)
        
        # About
        about_action = QAction("About", menu)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)
        
        menu.addSeparator()
        
        # Quit
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        
        # On macOS, clicking the tray icon shows the context menu automatically
        # Settings can be accessed via the menu
        
        self.tray_icon.show()
        logger.debug("System tray icon created")

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
                "Hotkeys unavailable",
                "Grant Accessibility and Input Monitoring permissions, then restart LingoFlow.",
            )

    def _format_hotkey(self, action: str) -> str:
        """Format hotkey for display in menu."""
        if action == "translate":
            hotkey = self.settings.hotkeys.translate
        elif action == "ocr":
            hotkey = self.settings.hotkeys.ocr
        else:
            return ""
        
        # Simple formatting
        display = hotkey.replace("<alt>", "⌥").replace("<cmd>", "⌘")
        display = display.replace("<ctrl>", "⌃").replace("<shift>", "⇧")
        display = display.replace("+", "")
        return display.upper()

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
        if self._is_translating or self._is_processing_ocr:
            logger.debug("Translation or OCR already in progress, ignoring")
            return
        
        # Quick check if Ollama is available
        if not self.translator.is_available():
            self._show_notification(
                "Ollama not running",
                "Start Ollama with 'ollama serve'"
            )
            self._update_status("Ollama offline")
            return
        
        # Get selected text
        selected_text = self.clipboard.get_selected_text()
        
        if not selected_text or not selected_text.strip():
            logger.debug("No text selected")
            self._show_notification("No text selected", "Select some text and try again.")
            return
        
        selected_text = selected_text.strip()
        
        # Limit text length to prevent very long translations
        max_length = 5000
        if len(selected_text) > max_length:
            logger.warning(f"Text too long ({len(selected_text)} chars), truncating")
            selected_text = selected_text[:max_length] + "..."
        
        if self.settings.privacy.allow_content_logging:
            logger.info(f"Translating selected text: {selected_text[:80]}...")
        else:
            logger.info(f"Translating selected text ({len(selected_text)} chars)")
        
        # Show popup
        self._ensure_popup()
        self.popup.show_with_text(
            selected_text,
            source_language=self.settings.translation.source_language,
        )
        
        # Start translation in background
        self._start_translation(selected_text)

    def _on_ocr_requested(self) -> None:
        """Handle OCR request (main thread)."""
        if self._is_translating or self._is_processing_ocr:
            logger.debug("Translation or OCR already in progress, ignoring")
            return
        
        logger.info("Starting OCR capture")
        self._update_status("Capturing...")
        
        # Capture screen selection on the main thread, then perform OCR in a worker.
        try:
            image_path = self.ocr_service.capture_interactive()
        except ScreenCaptureError as e:
            logger.error(f"OCR capture failed: {e}")
            self._show_notification("OCR Error", str(e))
            self._update_status("Ready")
            return
        
        if image_path is None:
            logger.debug("OCR cancelled by user")
            self._update_status("Ready")
            return

        self._is_processing_ocr = True
        self._update_status("Recognizing...")

        self._active_ocr_task = self._task_runner.create("ocr")
        self._active_ocr_task.start(lambda task: self._ocr_worker(task, image_path))

    def _ocr_worker(self, task: BackgroundTask, image_path) -> None:
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
            self.signals.ocr_finished.emit(task.task_id, result)

    def _on_ocr_finished(self, task_id: int, result: OCRResult) -> None:
        """Handle OCR completion (main thread)."""
        if not self._is_active_ocr_task(task_id):
            logger.debug(f"Ignoring stale OCR finish signal: {task_id}")
            return

        self._is_processing_ocr = False
        self._active_ocr_task = None

        if not result.success:
            logger.error(f"OCR failed: {result.error_message}")
            self._show_notification("OCR Error", result.error_message or "OCR failed.")
            self._update_status("Ready")
            return
        
        if not result.text or not result.text.strip():
            logger.debug("No text extracted from image")
            self._show_notification("No text found", "Could not extract text from the selected area.")
            self._update_status("Ready")
            return
        
        extracted_text = result.text.strip()
        if self.settings.privacy.allow_content_logging:
            logger.info(f"OCR extracted text: {extracted_text[:80]}...")
        else:
            logger.info(f"OCR extracted text ({len(extracted_text)} chars)")
        
        # Show popup with extracted text
        self._ensure_popup()
        self.popup.show_with_text(
            extracted_text,
            source_language=self.settings.translation.source_language,
        )
        
        # Start translation
        self._start_translation(extracted_text)
    
    def _on_translation_finished(self, task_id: int) -> None:
        """Handle translation completion (main thread)."""
        if not self._is_active_translation_task(task_id):
            logger.debug(f"Ignoring stale translation finish signal: {task_id}")
            return

        self._is_translating = False
        self._active_translation_task = None
        self._update_status("Ready")

    def _on_translation_chunk(self, task_id: int, chunk: str) -> None:
        """Append a translation chunk for the active task."""
        if not self._is_active_translation_task(task_id) or not self.popup:
            return
        self.popup.append_translation(chunk)

    def _on_translation_cleared(self, task_id: int) -> None:
        """Clear translation output for the active task."""
        if not self._is_active_translation_task(task_id) or not self.popup:
            return
        self.popup.clear_translation()

    def _on_translation_error(self, task_id: int, message: str) -> None:
        """Show a translation error for the active task."""
        if not self._is_active_translation_task(task_id) or not self.popup:
            return
        self.popup.show_error(message)

    def _on_translation_completed(self, task_id: int) -> None:
        """Mark popup translation complete for the active task."""
        if not self._is_active_translation_task(task_id) or not self.popup:
            return
        self.popup.finish_translation()

    # -------------------------------------------------------------------------
    # Translation Logic
    # -------------------------------------------------------------------------

    def _start_translation(self, text: str) -> None:
        """Start translation in a background thread."""
        self._is_translating = True
        self._update_status("Translating...")
        
        # Notify popup
        self.popup.start_translation()
        
        # Get target language from popup
        target_lang = self.popup.get_target_language()

        task = self._task_runner.create("translation")
        self._active_translation_task = task
        task.start(lambda task: self._translate_worker(task, text, target_lang))

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
                        # Check if this translation was cancelled
                        if task.is_cancelled():
                            logger.info("Translation cancelled")
                            return
                        self.signals.translation_chunk.emit(task.task_id, chunk)
                    
                    # Finished successfully
                    if task.is_cancelled():
                        logger.info("Translation cancelled")
                        return
                    self.signals.translation_completed.emit(task.task_id)
                    
                    logger.info("Translation completed")
                    break  # Success, exit retry loop
                    
                except OllamaConnectionError as e:
                    if task.is_cancelled():
                        logger.info("Translation cancelled")
                        return

                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(f"Connection failed, retrying ({retry_count}/{max_retries})...")
                        if task.cancel_event.wait(timeout=1.0):
                            logger.info("Translation cancelled")
                            return
                        self.signals.translation_cleared.emit(task.task_id)
                    else:
                        logger.error(f"Ollama connection error after {max_retries} retries: {e}")
                        self.signals.translation_error.emit(
                            task.task_id,
                            "Cannot connect to Ollama.\n"
                            "Make sure it's running: ollama serve",
                        )
        
        except OllamaError as e:
            if task.is_cancelled():
                logger.info("Translation cancelled")
                return

            logger.error(f"Ollama error: {e}")
            self.signals.translation_error.emit(task.task_id, str(e))
        
        except Exception as e:
            if task.is_cancelled():
                logger.info("Translation cancelled")
                return

            logger.error(f"Translation error: {e}")
            self.signals.translation_error.emit(task.task_id, f"Translation failed: {e}")
        
        finally:
            if not task.is_cancelled():
                self.signals.translation_finished.emit(task.task_id)

    # -------------------------------------------------------------------------
    # UI Helpers
    # -------------------------------------------------------------------------

    def _ensure_popup(self) -> None:
        """Ensure popup window exists."""
        if self.popup is None:
            self.popup = TranslationPopup(self.settings)
            self.popup.language_changed.connect(self._on_popup_language_changed)
            self.popup.closed.connect(self._on_popup_closed)

    def _dismiss_popup(self, reason: str) -> None:
        """Dismiss the popup even if macOS has hidden it outside Qt visibility state."""
        if not self.popup:
            return

        logger.debug(reason)
        try:
            self.popup.dismiss()
        except RuntimeError:
            self.popup = None

    def _is_active_translation_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active translation."""
        return (
            self._is_translating
            and self._active_translation_task is not None
            and self._active_translation_task.task_id == task_id
            and not self._active_translation_task.is_cancelled()
        )

    def _is_active_ocr_task(self, task_id: int) -> bool:
        """Return whether a task still owns the active OCR operation."""
        return (
            self._is_processing_ocr
            and self._active_ocr_task is not None
            and self._active_ocr_task.task_id == task_id
            and not self._active_ocr_task.is_cancelled()
        )

    def _cancel_active_translation(self, reason: str, update_status: bool = True) -> None:
        """Cancel the active translation task if one is running."""
        if not self._is_translating:
            return

        logger.info(reason)
        self._task_runner.cancel(self._active_translation_task)
        self.translator.cancel()
        self._is_translating = False
        self._active_translation_task = None

        if update_status:
            self._update_status("Ready")

    def _on_popup_closed(self) -> None:
        """Cancel translation work when the popup is dismissed."""
        self._cancel_active_translation("Popup closed, cancelling active translation")
        self.popup = None

    def _on_popup_language_changed(self, language: str) -> None:
        """Re-translate when user changes target language in popup."""
        # Cancel any in-progress translation
        self._cancel_active_translation(
            "Target language changed, cancelling current translation",
            update_status=False,
        )
        
        source_text = self.popup.get_source_text()
        if source_text:
            # Clear previous translation and re-run (without repositioning)
            self.popup.clear_translation()
            self._start_translation(source_text)

    def _update_status(self, status: str) -> None:
        """Update tray icon status."""
        if status == "Ready":
            self.status_action.setText("● Ready")
            self.tray_icon.setToolTip(f"{APP_NAME} - Ready")
        elif status == "Translating...":
            self.status_action.setText("◐ Translating...")
            self.tray_icon.setToolTip(f"{APP_NAME} - Translating...")
        elif status == "Capturing...":
            self.status_action.setText("◐ Capturing...")
            self.tray_icon.setToolTip(f"{APP_NAME} - Capturing...")
        elif status == "Recognizing...":
            self.status_action.setText("◐ Recognizing...")
            self.tray_icon.setToolTip(f"{APP_NAME} - Recognizing text...")
        else:
            self.status_action.setText(f"● {status}")
            self.tray_icon.setToolTip(f"{APP_NAME} - {status}")

    def _show_notification(self, title: str, message: str) -> None:
        """Show a system notification."""
        if self.tray_icon and self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000,  # 3 seconds
            )

    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show an error dialog."""
        QMessageBox.critical(None, title, message)

    def handle_external_launch(self) -> None:
        """Handle a second launch while this instance is already running."""
        if self._onboarding_dialog:
            self._activate_app_for_dialog()
            self._onboarding_dialog.show_for_user()
            return

        if self._settings_dialog_open:
            self._raise_dialog(self._settings_dialog)
            return

        self._activate_app_for_dialog()
        self._show_notification(
            f"{APP_NAME} is already running",
            "Use the menu bar icon to translate, run OCR, or open settings.",
        )

    # -------------------------------------------------------------------------
    # Menu Actions
    # -------------------------------------------------------------------------

    def _show_settings(self) -> None:
        """Show the settings dialog."""
        # Prevent multiple dialogs from opening
        if self._settings_dialog_open:
            self._raise_dialog(self._settings_dialog)
            return

        self._dismiss_popup("Opening settings, closing any existing popup")
        
        self._settings_dialog_open = True

        dialog = SettingsDialog(self.settings)
        self._settings_dialog = dialog
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.finished.connect(lambda _: self._on_settings_closed(dialog))
        self._activate_app_for_dialog()
        QTimer.singleShot(0, lambda: self._raise_dialog(dialog))
        QTimer.singleShot(150, lambda: self._raise_dialog(dialog))
        dialog.show()

    def _on_settings_closed(self, dialog: SettingsDialog) -> None:
        """Clear settings dialog state after a modeless settings window closes."""
        if dialog is not self._settings_dialog:
            return

        self._settings_dialog = None
        self._settings_dialog_open = False
        dialog.deleteLater()

    def _activate_app_for_dialog(self) -> None:
        """Bring this tray app forward before showing a real dialog on macOS."""
        if platform.system() != "Darwin":
            return

        try:
            from AppKit import NSApplication

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception as e:
            logger.debug(f"Could not activate app for dialog: {e}")

    def _raise_dialog(self, dialog) -> None:
        """Show and foreground an existing dialog."""
        if dialog is None:
            return

        try:
            self._activate_app_for_dialog()
            if not dialog.isVisible():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except RuntimeError:
            pass

    def _on_settings_changed(self, new_settings: AppSettings) -> None:
        """Handle settings changes."""
        self.settings = new_settings
        
        # Update services
        self.translator.update_settings(new_settings)
        self.ocr_service.update_settings(new_settings)
        self.hotkey_manager.update_settings(new_settings)
        
        # Update popup if it exists
        if self.popup:
            self.popup.update_settings(new_settings)
        
        logger.info("Settings applied to all services")

    def _show_onboarding(self, force: bool = False) -> None:
        """Show first-run setup when needed."""
        if not self.permission_service:
            return

        if self._onboarding_dialog:
            self._activate_app_for_dialog()
            self._onboarding_dialog.show_for_user()
            return

        permissions_ready = self.permission_service.required_permissions_ready()
        if not force and self.settings.onboarding.completed and permissions_ready:
            return

        dialog = OnboardingDialog(self.permission_service)
        self._onboarding_dialog = dialog
        dialog.finished.connect(lambda _: self._on_onboarding_finished(dialog))
        dialog.restart_requested.connect(self._restart_app)
        self._activate_app_for_dialog()
        dialog.show_for_user()

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
        """Show about dialog."""
        QMessageBox.about(
            None,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Version {APP_VERSION}</p>"
            f"<p>A lightweight, Ollama-powered translation app with OCR support.</p>"
            f"<p>Built with PyQt6 and Apple Vision.</p>"
            f"<hr>"
            f"<p><b>Hotkeys:</b></p>"
            f"<p>• {self._format_hotkey('translate')} - Translate selected text</p>"
            f"<p>• {self._format_hotkey('ocr')} - OCR screenshot</p>"
        )

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

        # Stop any active translation
        self._cancel_active_translation("Quitting, cancelling active translation", update_status=False)
        self._task_runner.cancel(self._active_ocr_task)
        self._active_ocr_task = None
        self._is_processing_ocr = False
        
        # Stop hotkey listener
        self.hotkey_manager.stop()
        
        # Hide tray icon
        if self.tray_icon:
            self.tray_icon.hide()

        if self._onboarding_dialog:
            self._onboarding_dialog.close()
            self._onboarding_dialog = None
        
        # Quit application
        QApplication.quit()

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the application (called after QApplication.exec())."""
        self._show_onboarding()
        self._start_hotkeys()

        # Check Ollama connection on startup
        if not self.translator.is_available():
            self._show_notification(
                "Ollama not running",
                "Start Ollama with 'ollama serve' for translations to work."
            )
            self._update_status("Ollama offline")
            logger.warning("Ollama is not available at startup")
        else:
            # Verify the configured model exists
            available_models = self.translator.get_available_models()
            configured_model = self.settings.ollama.model
            
            if available_models and configured_model not in available_models:
                fallback_model = available_models[0]
                self._show_notification(
                    "Model not found",
                    f"Using '{fallback_model}' for this session."
                )
                logger.warning(
                    f"Configured model '{configured_model}' not found; "
                    f"using session fallback '{fallback_model}'"
                )
                runtime_settings = self.settings.model_copy(deep=True)
                runtime_settings.ollama.model = fallback_model
                self.translator.update_settings(runtime_settings)
            
            self._update_status("Ready")
            logger.info("Ollama connection verified")
