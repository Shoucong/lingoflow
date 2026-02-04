"""
Main window and system tray controller for LingoFlow.

This is the central hub that connects:
- Hotkey manager (input triggers)
- Translation service (processing)
- Popup window (output display)
- Settings dialog (configuration)
"""

import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
)

from lingoflow.config.settings import AppSettings
from lingoflow.config.constants import APP_NAME, APP_VERSION
from lingoflow.core.hotkey import HotkeyManager, HotkeyAction
from lingoflow.core.translator import TranslationService
from lingoflow.core.ocr import OCRService
from lingoflow.infrastructure.clipboard import ClipboardManager
from lingoflow.infrastructure.ollama_client import OllamaConnectionError, OllamaError
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
    translation_finished = pyqtSignal()  # translation completed


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
        
        # UI components
        self.popup: Optional[TranslationPopup] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        
        # State
        self._is_translating = False
        self._current_translation_thread: Optional[threading.Thread] = None
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
        self.signals.translation_finished.connect(self._on_translation_finished)

    def _setup_tray(self) -> None:
        """Set up the system tray icon and menu."""
        self.tray_icon = QSystemTrayIcon()
        
        # Set icon (using a text-based icon for now)
        # TODO: Replace with actual icon file
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
        
        # Start listening
        self.hotkey_manager.start()
        logger.info("Hotkeys registered and listening")

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
        if self._is_translating:
            logger.debug("Translation already in progress, ignoring")
            return
        
        # Get selected text
        selected_text = self.clipboard.get_selected_text()
        
        if not selected_text or not selected_text.strip():
            logger.debug("No text selected")
            self._show_notification("No text selected", "Select some text and try again.")
            return
        
        selected_text = selected_text.strip()
        logger.info(f"Translating: {selected_text[:50]}...")
        
        # Show popup
        self._ensure_popup()
        self.popup.show_with_text(selected_text)
        
        # Start translation in background
        self._start_translation(selected_text)

    def _on_ocr_requested(self) -> None:
        """Handle OCR request (main thread)."""
        if self._is_translating:
            logger.debug("Translation already in progress, ignoring")
            return
        
        logger.info("Starting OCR capture")
        self._update_status("Capturing...")
        
        # Capture screen (this will show the selection UI)
        result = self.ocr_service.capture_and_extract()
        
        if not result.success:
            if result.error_message == "Screen capture cancelled":
                logger.debug("OCR cancelled by user")
                self._update_status("Ready")
            else:
                logger.error(f"OCR failed: {result.error_message}")
                self._show_notification("OCR Error", result.error_message)
                self._update_status("Ready")
            return
        
        if not result.text or not result.text.strip():
            logger.debug("No text extracted from image")
            self._show_notification("No text found", "Could not extract text from the selected area.")
            self._update_status("Ready")
            return
        
        extracted_text = result.text.strip()
        logger.info(f"OCR extracted: {extracted_text[:50]}...")
        
        # Show popup with extracted text
        self._ensure_popup()
        self.popup.show_with_text(extracted_text)
        
        # Start translation
        self._start_translation(extracted_text)
    
    def _on_translation_finished(self) -> None:
        """Handle translation completion (main thread)."""
        self._is_translating = False
        self._update_status("Ready")

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
        
        # Run in background thread
        self._current_translation_thread = threading.Thread(
            target=self._translate_worker,
            args=(text, target_lang),
            daemon=True,
        )
        self._current_translation_thread.start()

    def _translate_worker(self, text: str, target_language: str) -> None:
        """Background worker for translation."""
        try:
            for chunk in self.translator.translate_stream(
                text,
                target_language=target_language,
            ):
                if self.popup:
                    self.popup.append_translation(chunk)
            
            # Finished successfully
            if self.popup:
                self.popup.finish_translation()
            
            logger.info("Translation completed")
            
        except OllamaConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            if self.popup:
                self.popup.show_error("Cannot connect to Ollama. Make sure it's running.")
        
        except OllamaError as e:
            logger.error(f"Ollama error: {e}")
            if self.popup:
                self.popup.show_error(str(e))
        
        except Exception as e:
            logger.error(f"Translation error: {e}")
            if self.popup:
                self.popup.show_error(f"Translation failed: {e}")
        
        finally:
            # Use signal to update on main thread (thread-safe)
            self.signals.translation_finished.emit()

    # -------------------------------------------------------------------------
    # UI Helpers
    # -------------------------------------------------------------------------

    def _ensure_popup(self) -> None:
        """Ensure popup window exists."""
        if self.popup is None:
            self.popup = TranslationPopup(self.settings)

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

    # -------------------------------------------------------------------------
    # Menu Actions
    # -------------------------------------------------------------------------

    def _show_settings(self) -> None:
        """Show the settings dialog."""
        # Prevent multiple dialogs from opening
        if self._settings_dialog_open:
            return
        
        self._settings_dialog_open = True
        
        try:
            dialog = SettingsDialog(self.settings)
            dialog.settings_changed.connect(self._on_settings_changed)
            dialog.exec()
        finally:
            self._settings_dialog_open = False

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

    def _quit(self) -> None:
        """Quit the application."""
        logger.info("Quitting application")
        
        # Stop hotkey listener
        self.hotkey_manager.stop()
        
        # Hide tray icon
        if self.tray_icon:
            self.tray_icon.hide()
        
        # Quit application
        QApplication.quit()

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the application (called after QApplication.exec())."""
        # Check Ollama connection on startup
        if not self.translator.is_available():
            self._show_notification(
                "Ollama not running",
                "Start Ollama with 'ollama serve' for translations to work."
            )
            self._update_status("Ollama offline")
        else:
            self._update_status("Ready")
            logger.info("Ollama connection verified")