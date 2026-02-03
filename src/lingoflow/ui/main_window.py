"""
Main window and system tray controller for LingoFlow.

This is the central hub that connects:
- Hotkey manager (input triggers)
- Translation service (processing)
- Popup window (output display)
- Settings dialog (configuration)
"""

from sys import thread_info
from anyio._core._eventloop import reset_current_async_library
from __unknown__ import selected_lang
from PyQt6.QtWidgets import QGraphicsPolygonItem
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
# Signal Beidge for Cross-Thread Communication
# =============================================================================


class MainSignals(QObject):
    """Signals for thread-safe communication from hotkey callbacks."""

    translate_requested = pyqtSignal()
    ocr_requested = pyqtSignal()
    show_error = pyqtSignal(str, str) # title, message


# =========================================================
# Main Controlller
# =========================================================

class MainController(QObject):
    """
    Main application controller. 

    Manages:
    - System tray icon and menu
    - Gllobal hotkey handling
    - Translation workfloww
    - OCR workflow
    - Settings Management

    This class coordinates all the pieces but doesn't create a visiable window.
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

        self._setup_signals()
        self._setup_tray()
        self._setup_hotkeys()

        logger.info(f"{APP_NAME} v{APP_VERSION} initialized")
    
    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_signals(self) -> None:
        """Connect cross-thread signals."""
        self.signals.translate_requested.connect(self._on_translate_requested)
        self.signals.ocr_requested.connect(self._on_ocr_requested)
        self.signals.show_error.connect(self._show_error_dialog)

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
        self.status_action = QAction("● Ready")
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        
        menu.addSeparator()
        
        # Translate action
        translate_action = QAction(f"Translate Selection ({self._format_hotkey('translate')})")
        translate_action.triggered.connect(self._on_translate_requested)
        menu.addAction(translate_action)
        
        # OCR action
        ocr_action = QAction(f"OCR Screenshot ({self._format_hotkey('ocr')})")
        ocr_action.triggered.connect(self._on_ocr_requested)
        menu.addAction(ocr_action)
        
        menu.addSeparator()
        
        # Settings
        settings_action = QAction("Settings...")
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)
        
        # About
        about_action = QAction("About")
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)
        
        menu.addSeparator()
        
        # Quit
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        
        # Double-click opens settings
        self.tray_icon.activated.connect(self._on_tray_activated)
        
        self.tray_icon.show()
        logger.debug("System tray icon created")

    def _setup_hotkeys(self) -> None:
        """Register global hotheys. """
        # Register global hotkeys
        self.hotkey_manager.register(
            HotkeyAction.TRANSLATE, 
            self.settings.hotkeys.translate,
            self._on_hotkey_translate, 
            description="Translate selected text",
        )
        
        # Regisiter OCR hotkey
        self.hotkey_manager.register(
            HotkeyAction.OCR, 
            self.settings.hotkeys.ocr,
            self._on_hotkey_ocr, 
            description="OCR screenshot and translalte",
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
    
    # =============================================================================
    # Hotkey Callbacks (Called from Background Thread)
    # =============================================================================
    
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
    
    # =============================================================================
    # Main Thread Handlers
    # =============================================================================
    
    def _on_translate_requested(self) -> None:
        """Handle translate request on main thread."""
        if self._is_translating:
            logger.debug("Translation already in progress, ignoring")
            return 
        
        # Get selected text
        selected_text = self.clipboard.get_selected_text()

        if not selected_text or not selected_text.strip():
            logger.debug("No text selected")
            self._show_notification("No text selected", "Selected some text and try again")
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
    
    # =============================================================================
    # Translation Logic
    # =============================================================================

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
    
