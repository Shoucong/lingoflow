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
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)
    
    def _setup_ui(self) -> None:
        """Build the UI. """
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.tabs.addTab(self._create_general_tab(), "General")
        self.tabs.addTab(self._create_translation_tab(), "Translation")
        self.tabs.addTab(self._create_hotkeys_tab(), "Hotkeys")
        self.tabs.addTab(self._create_appearance_tab(), "Appearance")
        self.tabs.addTab(self._create_ocr_tab(), "OCR")

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)
    
    # =============================================================================
    # Tab Creation
    # =============================================================================
    
    def _create_general_tab(self) -> QWidget:
        """Create the General tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Ollama Connection Group
        ollama_group = QGroupBox("Ollama Connection")
        ollama_layout = QFormLayout(ollama_group)

        # Host
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("http://localhost:11434")
        ollama_layout.addRow("Ollama Host:", self.host_input)

        # Test connection button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        test_layout.addWidget(self.test_btn)

        