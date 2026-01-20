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
        self._available_models: List[str] = []
        
        self._setup_window()
        self._setup_ui()
        self._load_settings()
        
        logger.debug("SettingsDialog initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure dialog window."""
        self.setWindowTitle("LingoFlow Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)

    def _setup_ui(self) -> None:
        """Build the UI."""
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
        """Create the General settings tab."""
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
        
        self.connection_status = QLabel("")
        test_layout.addWidget(self.connection_status)
        test_layout.addStretch()
        
        ollama_layout.addRow("", test_layout)
        
        # Model selection
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(200)
        model_layout.addWidget(self.model_combo)
        
        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.refresh_models_btn)
        model_layout.addStretch()
        
        ollama_layout.addRow("Model:", model_layout)
        
        layout.addWidget(ollama_group)
        layout.addStretch()
        
        return tab

    def _create_translation_tab(self) -> QWidget:
        """Create the Translation settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Language Settings Group
        lang_group = QGroupBox("Default Languages")
        lang_layout = QFormLayout(lang_group)
        
        # Source language
        self.source_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            display_name = "Auto-detect" if lang == "auto" else lang
            self.source_lang_combo.addItem(display_name, lang)
        lang_layout.addRow("Source Language:", self.source_lang_combo)
        
        # Target language
        self.target_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            if lang != "auto":
                self.target_lang_combo.addItem(lang, lang)
        lang_layout.addRow("Target Language:", self.target_lang_combo)
        
        layout.addWidget(lang_group)
        
        # Advanced Group
        advanced_group = QGroupBox("Advanced")
        advanced_layout = QFormLayout(advanced_group)
        
        # Custom prompt (future feature)
        self.custom_prompt_check = QCheckBox("Use custom system prompt")
        self.custom_prompt_check.setEnabled(False)  # Future feature
        advanced_layout.addRow("", self.custom_prompt_check)
        
        layout.addWidget(advanced_group)
        layout.addStretch()
        
        return tab

    def _create_hotkeys_tab(self) -> QWidget:
        """Create the Hotkeys settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Hotkeys Group
        hotkeys_group = QGroupBox("Global Hotkeys")
        hotkeys_layout = QFormLayout(hotkeys_group)
        
        # Translate hotkey
        self.translate_hotkey_input = QLineEdit()
        self.translate_hotkey_input.setPlaceholderText("<alt>+d")
        hotkeys_layout.addRow("Translate Selected:", self.translate_hotkey_input)
        
        # OCR hotkey
        self.ocr_hotkey_input = QLineEdit()
        self.ocr_hotkey_input.setPlaceholderText("<alt>+s")
        hotkeys_layout.addRow("OCR Screenshot:", self.ocr_hotkey_input)
        
        layout.addWidget(hotkeys_group)
        
        # Help text
        help_label = QLabel(
            "Hotkey format: <alt>+d, <cmd>+<shift>+t, etc.\n"
            "Modifiers: <alt>, <ctrl>, <cmd>, <shift>\n"
            "Note: On macOS, <alt> is the Option key."
        )
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        layout.addStretch()
        
        return tab

    def _create_appearance_tab(self) -> QWidget:
        """Create the Appearance settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Theme Group
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        theme_layout.addRow("Theme:", self.theme_combo)
        
        layout.addWidget(theme_group)
        
        # Popup Group
        popup_group = QGroupBox("Popup Window")
        popup_layout = QFormLayout(popup_group)
        
        # Font size
        font_size_layout = QHBoxLayout()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 24)
        self.font_size_spin.setSuffix(" px")
        font_size_layout.addWidget(self.font_size_spin)
        font_size_layout.addStretch()
        popup_layout.addRow("Font Size:", font_size_layout)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_label = QLabel("95%")
        self.opacity_label.setMinimumWidth(40)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
        opacity_layout.addWidget(self.opacity_label)
        popup_layout.addRow("Opacity:", opacity_layout)
        
        # Show source text
        self.show_source_check = QCheckBox("Show source text in popup")
        popup_layout.addRow("", self.show_source_check)
        
        layout.addWidget(popup_group)
        layout.addStretch()
        
        return tab

    def _create_ocr_tab(self) -> QWidget:
        """Create the OCR settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # OCR Settings Group
        ocr_group = QGroupBox("OCR Settings")
        ocr_layout = QFormLayout(ocr_group)
        
        # OCR Language
        self.ocr_lang_combo = QComboBox()
        ocr_languages = [
            ("English", "eng"),
            ("Chinese Simplified", "chi_sim"),
            ("Chinese Traditional", "chi_tra"),
            ("Japanese", "jpn"),
            ("Korean", "kor"),
            ("English + Chinese", "eng+chi_sim"),
            ("English + Japanese", "eng+jpn"),
        ]
        for display, code in ocr_languages:
            self.ocr_lang_combo.addItem(display, code)
        ocr_layout.addRow("OCR Language:", self.ocr_lang_combo)
        
        # Enhance image
        self.enhance_image_check = QCheckBox("Enhance image before OCR")
        self.enhance_image_check.setToolTip(
            "Apply contrast and sharpening to improve accuracy"
        )
        ocr_layout.addRow("", self.enhance_image_check)
        
        layout.addWidget(ocr_group)
        
        # Info
        info_label = QLabel(
            "On macOS, OCR uses Apple Vision framework.\n"
            "No additional installation required."
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        return tab

    # =============================================================================
    # Settings Load/Save
    # =============================================================================

    def _load_settings(self) -> None:
        """Load current settings into UI."""
        s = self.settings
        
        # General
        self.host_input.setText(s.ollama.host)
        self.model_combo.setCurrentText(s.ollama.model)
        
        # Translation
        source_index = self.source_lang_combo.findData(s.translation.source_language)
        if source_index >= 0:
            self.source_lang_combo.setCurrentIndex(source_index)
        
        target_index = self.target_lang_combo.findData(s.translation.target_language)
        if target_index >= 0:
            self.target_lang_combo.setCurrentIndex(target_index)
        
        # Hotkeys
        self.translate_hotkey_input.setText(s.hotkeys.translate)
        self.ocr_hotkey_input.setText(s.hotkeys.ocr)
        
        # Appearance
        theme_index = self.theme_combo.findText(s.ui.theme.capitalize())
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        
        self.font_size_spin.setValue(s.ui.font_size)
        self.opacity_slider.setValue(int(s.ui.popup_opacity * 100))
        self.show_source_check.setChecked(s.ui.show_source_text)
        
        # OCR
        ocr_index = self.ocr_lang_combo.findData(s.ocr.language)
        if ocr_index >= 0:
            self.ocr_lang_combo.setCurrentIndex(ocr_index)
        self.enhance_image_check.setChecked(s.ocr.enhance_image)
        
        logger.debug("Settings loaded into UI")

    def _save_settings(self) -> None:
        """Save UI values to settings."""
        s = self.settings
        
        # General
        s.ollama.host = self.host_input.text().strip() or s.ollama.host
        s.ollama.model = self.model_combo.currentText().strip() or s.ollama.model
        
        # Translation
        s.translation.source_language = self.source_lang_combo.currentData()
        s.translation.target_language = self.target_lang_combo.currentData()
        
        # Hotkeys
        translate_hotkey = self.translate_hotkey_input.text().strip()
        if translate_hotkey:
            s.hotkeys.translate = translate_hotkey
        
        ocr_hotkey = self.ocr_hotkey_input.text().strip()
        if ocr_hotkey:
            s.hotkeys.ocr = ocr_hotkey
        
        # Appearance
        s.ui.theme = self.theme_combo.currentText().lower()
        s.ui.font_size = self.font_size_spin.value()
        s.ui.popup_opacity = self.opacity_slider.value() / 100.0
        s.ui.show_source_text = self.show_source_check.isChecked()
        
        # OCR
        s.ocr.language = self.ocr_lang_combo.currentData()
        s.ocr.enhance_image = self.enhance_image_check.isChecked()
        
        # Persist to disk
        s.save()
        
        # Emit signal
        self.settings_changed.emit(s)
        
        logger.info("Settings saved")
        self.accept()

    def _reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.settings = AppSettings()
            self._load_settings()
            logger.info("Settings reset to defaults")

    # =============================================================================
    # Ollama Connection
    # =============================================================================

    def _test_connection(self) -> None:
        """Test the Ollama connection."""
        host = self.host_input.text().strip() or self.settings.ollama.host
        
        self.connection_status.setText("Testing...")
        self.connection_status.setStyleSheet("color: gray;")
        self.test_btn.setEnabled(False)
        
        # Use QTimer to not block UI
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._do_test_connection(host))

    def _do_test_connection(self, host: str) -> None:
        """Perform the actual connection test."""
        try:
            client = OllamaClient(host=host)
            if client.is_available():
                self.connection_status.setText("✓ Connected")
                self.connection_status.setStyleSheet("color: green;")
                # Also refresh models
                self._refresh_models()
            else:
                self.connection_status.setText("✗ Not available")
                self.connection_status.setStyleSheet("color: red;")
        except Exception as e:
            self.connection_status.setText(f"✗ Error: {e}")
            self.connection_status.setStyleSheet("color: red;")
        finally:
            self.test_btn.setEnabled(True)

    def _refresh_models(self) -> None:
        """Refresh the list of available models."""
        host = self.host_input.text().strip() or self.settings.ollama.host
        
        try:
            client = OllamaClient(host=host)
            models = client.list_models()
            
            current_model = self.model_combo.currentText()
            self.model_combo.clear()
            
            for model in models:
                self.model_combo.addItem(model.name)
            
            # Restore previous selection if still available
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            elif self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
            
            logger.debug(f"Refreshed models: {[m.name for m in models]}")
            
        except OllamaError as e:
            logger.warning(f"Failed to refresh models: {e}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to fetch models: {e}\n\nMake sure Ollama is running.",
            )