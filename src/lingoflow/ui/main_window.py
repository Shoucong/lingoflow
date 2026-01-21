"""
Main window and system tray controller for LingoFlow.

This is the central hub that connects: 
- Hotkey manager (input triggers)
- Translation service (processing)
- Popup window (output)
- Settings dialog (configuration)
"""

import threading
from typing import Optional

from PyQt6.QtCode import Qt, QTimer, pyqtSignal, QObject
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
from lingoflow.core.translation import TranslationService
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
    