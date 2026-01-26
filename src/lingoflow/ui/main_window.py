"""
Main window and system tray controller for LingoFlow.

This is the central hub that connects:
- Hotkey manager (input triggers)
- Translation service (processing)
- Popup window (output display)
- Settings dialog (configuration)
"""

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