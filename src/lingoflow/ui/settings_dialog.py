"""
Settings dialog for LingoFlow. 

Provides UI for configuring all app settings. 
"""

from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSlider,
    QSpinBox,
    QPushButton,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QFrame,
)

from lingoflow.config.settings import AppSettings
from lingoflow.config.constants import SUPPORTED_LANGUAGES
from lingoflow.infrastructure.ollama_client import OllamaClient, OllamaError
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

class SettingsDialog(QDialog):
    """
    Settings configuration dialog. 

    Organized into tabs:
    - General: Ollama connection, model selection
    - Translation: Source/target language defaults
    - Hotkeys: Keyboard shortcut configuration
    - Appearance: UI theme, font size, opacity
    - OCR: OCR language settings

    Emits:
        settings_changed: When settings are saved
    """

    settings_changed = pyqtSignal(AppSettings)

    def __init__(self, settings: Optional[AppSettings] = None, parent=None):
        super().__init__(parent)
        
        self.settings = settings or AppSettings.load()
        self.available_models: List[str] = []

        self._setup_window()
        self._setup_ui()
        self._load_settings()

        logger.debug("SettingsDialog initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure dialog window."""
        