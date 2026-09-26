"""
Settings dialog for LingoFlow.

Provides UI for configuring all app settings.
"""

from typing import List, Optional

from pydantic import ValidationError
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lingoflow.config.constants import SUPPORTED_LANGUAGES
from lingoflow.config.settings import AppSettings, OllamaSettings
from lingoflow.core.speech import LANGUAGE_LOCALES
from lingoflow.infrastructure.macos.speech import MacOSSpeechService
from lingoflow.infrastructure.ollama_client import OllamaClient, OllamaError
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui.theme import apply_palette
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
    connection_test_finished = pyqtSignal(int, bool, str)
    models_refresh_finished = pyqtSignal(int, object, str)

    def __init__(self, settings: Optional[AppSettings] = None, parent=None):
        super().__init__(parent)

        self.settings = settings or AppSettings.load()
        self._available_models: List[str] = []
        self._network_tasks = TaskRunner()
        self._active_connection_task_id: Optional[int] = None
        self._active_models_task_id: Optional[int] = None
        self._speech = MacOSSpeechService.shared()

        self._setup_window()
        self._setup_ui()
        self._load_settings()
        apply_palette(self, self.settings.ui.theme)
        self._speech.voices_changed.connect(self._update_speech_voice_choices)
        self.speech_locale_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.source_lang_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.target_lang_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.theme_combo.currentTextChanged.connect(self._preview_theme)
        self.connection_test_finished.connect(self._on_connection_test_finished)
        self.models_refresh_finished.connect(self._on_models_refresh_finished)

        logger.debug("SettingsDialog initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure dialog window."""
        self.setWindowTitle("LingoFlow Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.resize(620, 660)
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)

    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self._add_scroll_tab(self._create_general_tab(), "General")
        self._add_scroll_tab(self._create_languages_tab(), "Languages")
        self._add_scroll_tab(self._create_hotkeys_tab(), "Hotkeys")
        self._add_scroll_tab(self._create_appearance_tab(), "Appearance")
        self._speech_tab = self._add_scroll_tab(self._create_speech_tab(), "Speech")

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

    def _add_scroll_tab(self, content: QWidget, title: str) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QScrollArea.Shape.NoFrame)
        page.setWidget(content)
        self.tabs.addTab(page, title)
        return page

    def _preview_theme(self, theme: str) -> None:
        apply_palette(self, theme.lower())

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

        generation = QGroupBox("Model behavior")
        form = QFormLayout(generation)
        self.context_spin = QSpinBox()
        self.context_spin.setRange(2048, 131072)
        self.context_spin.setSingleStep(1024)
        form.addRow("Context window (tokens):", self.context_spin)
        self.output_spin = QSpinBox()
        self.output_spin.setRange(128, 32768)
        self.output_spin.setSingleStep(256)
        form.addRow("Output budget per part:", self.output_spin)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.05)
        form.addRow("Temperature:", self.temperature_spin)
        self.thinking_combo = QComboBox()
        self.thinking_combo.addItems(["off", "auto", "on"])
        form.addRow("Thinking (supported models):", self.thinking_combo)
        self.keep_alive_spin = QSpinBox()
        self.keep_alive_spin.setRange(0, 3600)
        self.keep_alive_spin.setSuffix(" s")
        form.addRow("Keep model loaded:", self.keep_alive_spin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" s")
        form.addRow("Generation read timeout:", self.timeout_spin)
        layout.addWidget(generation)

        privacy_group = QGroupBox("Privacy")
        privacy_layout = QFormLayout(privacy_group)

        self.allow_content_logging_check = QCheckBox("Include selected/OCR text in logs")
        self.allow_content_logging_check.setToolTip(
            "Off by default. Enable only while debugging because logs may include private text."
        )
        privacy_layout.addRow("", self.allow_content_logging_check)

        self.keep_ocr_captures_check = QCheckBox("Keep OCR screenshots for troubleshooting")
        self.keep_ocr_captures_check.setToolTip(
            "Off by default. When disabled, captured screenshots are deleted after OCR."
        )
        privacy_layout.addRow("", self.keep_ocr_captures_check)

        privacy_note = QLabel(
            "For normal use, leave both options off so reading content stays out of logs "
            "and temporary screenshots are cleaned up."
        )
        privacy_note.setStyleSheet("color: gray; font-size: 11px;")
        privacy_note.setWordWrap(True)
        privacy_layout.addRow("", privacy_note)

        layout.addWidget(privacy_group)
        layout.addStretch()

        return tab

    def _create_languages_tab(self) -> QWidget:
        """Create language settings for translation and OCR."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Language Settings Group
        lang_group = QGroupBox("Translation")
        lang_layout = QFormLayout(lang_group)

        # Source language
        self.source_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            display_name = "Auto-detect" if lang == "auto" else lang
            self.source_lang_combo.addItem(display_name, lang)
        lang_layout.addRow("Text Source:", self.source_lang_combo)

        # Target language
        self.target_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            if lang != "auto":
                self.target_lang_combo.addItem(lang, lang)
        lang_layout.addRow("Translate To:", self.target_lang_combo)

        layout.addWidget(lang_group)

        # OCR Settings Group
        ocr_group = QGroupBox("OCR Recognition")
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
        ocr_layout.addRow("Screenshot Text:", self.ocr_lang_combo)

        # Enhance image
        self.enhance_image_check = QCheckBox("Enhance image before OCR")
        self.enhance_image_check.setToolTip("Apply contrast and sharpening to improve accuracy")
        ocr_layout.addRow("", self.enhance_image_check)
        self.ocr_review_check = QCheckBox("Review and edit recognized text before translating")
        ocr_layout.addRow("", self.ocr_review_check)

        layout.addWidget(ocr_group)

        # Info
        info_label = QLabel(
            "Screenshot Text is the language inside the image for recognition. "
            "OCR results still translate to the Translate To language above."
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Advanced Group
        advanced_group = QGroupBox("Advanced")
        advanced_layout = QFormLayout(advanced_group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["faithful", "academic"])
        advanced_layout.addRow("Translation style:", self.preset_combo)
        self.custom_prompt_check = QCheckBox("Use custom system prompt")
        advanced_layout.addRow("", self.custom_prompt_check)
        self.custom_prompt_input = QTextEdit()
        self.custom_prompt_input.setAcceptRichText(False)
        self.custom_prompt_input.setMaximumHeight(120)
        self.custom_prompt_check.toggled.connect(self.custom_prompt_input.setEnabled)
        advanced_layout.addRow(self.custom_prompt_input)

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

    def _create_speech_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.speech_locale_combo = QComboBox()
        self.speech_locale_combo.addItem("English (US)", "en-US")
        self.speech_locale_combo.addItem("English (UK)", "en-GB")
        for language, locale in LANGUAGE_LOCALES.items():
            if language != "English":
                self.speech_locale_combo.addItem(language, locale)
        layout.addRow("Auto-source language / accent:", self.speech_locale_combo)
        self.source_voice_combo = QComboBox()
        self.target_voice_combo = QComboBox()
        layout.addRow("Source voice:", self.source_voice_combo)
        layout.addRow("Translation voice:", self.target_voice_combo)
        self.speech_rate_spin = QSpinBox()
        self.speech_rate_spin.setRange(80, 300)
        self.speech_rate_spin.setSuffix(" words/min")
        layout.addRow("Speaking rate:", self.speech_rate_spin)
        refresh = QPushButton("Refresh installed voices")
        refresh.clicked.connect(self._speech.refresh_voices)
        layout.addRow(refresh)
        note = QLabel(
            "Uses downloaded macOS voices. For more voices, open System Settings → "
            "Accessibility → Read & Speak. Source and translation use separate voices."
        )
        note.setWordWrap(True)
        layout.addRow(note)
        return tab

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self._speech_tab:
            self._speech.refresh_voices()

    def _update_speech_voice_choices(self, *_args) -> None:
        source = self.source_lang_combo.currentData()
        preferred_locale = self.speech_locale_combo.currentData()
        source_locale = LANGUAGE_LOCALES.get(source, preferred_locale)
        if source == "English" and preferred_locale.startswith("en-"):
            source_locale = preferred_locale
        target = self.target_lang_combo.currentData()
        target_locale = LANGUAGE_LOCALES.get(target, "")
        if target == "English" and preferred_locale.startswith("en-"):
            target_locale = preferred_locale
        for combo, locale, saved in [
            (self.source_voice_combo, source_locale, self.settings.speech.source_voice),
            (self.target_voice_combo, target_locale, self.settings.speech.target_voice),
        ]:
            current = combo.currentData() if combo.count() else saved
            combo.clear()
            combo.addItem("Automatic", "")
            for voice in self._speech.voices:
                if voice.locale == locale:
                    combo.addItem(voice.name, voice.name)
            if current and combo.findData(current) < 0:
                combo.addItem(f"{current} (unavailable for this language)", current)
            combo.setCurrentIndex(max(0, combo.findData(current)))

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
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_layout.addWidget(self.opacity_label)
        popup_layout.addRow("Opacity:", opacity_layout)

        # Show source text
        self.show_source_check = QCheckBox("Show source text in popup")
        popup_layout.addRow("", self.show_source_check)
        self.hide_focus_check = QCheckBox("Hide an unpinned window after losing focus")
        popup_layout.addRow("", self.hide_focus_check)
        self.bilingual_layout_combo = QComboBox()
        self.bilingual_layout_combo.addItem("Stacked", "stacked")
        self.bilingual_layout_combo.addItem("Side by side", "side_by_side")
        popup_layout.addRow("Text layout:", self.bilingual_layout_combo)

        layout.addWidget(popup_group)
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
        self.context_spin.setValue(s.ollama.context_window)
        self.output_spin.setValue(s.ollama.max_output_tokens)
        self.temperature_spin.setValue(s.ollama.temperature)
        self.thinking_combo.setCurrentText(s.ollama.thinking)
        self.keep_alive_spin.setValue(s.ollama.keep_alive)
        self.timeout_spin.setValue(int(s.ollama.read_timeout))

        # Translation
        source_index = self.source_lang_combo.findData(s.translation.source_language)
        if source_index >= 0:
            self.source_lang_combo.setCurrentIndex(source_index)

        target_index = self.target_lang_combo.findData(s.translation.target_language)
        if target_index >= 0:
            self.target_lang_combo.setCurrentIndex(target_index)
        self.preset_combo.setCurrentText(s.translation.preset)
        self.custom_prompt_check.setChecked(bool(s.translation.custom_prompt))
        self.custom_prompt_input.setPlainText(s.translation.custom_prompt or "")
        self.custom_prompt_input.setEnabled(bool(s.translation.custom_prompt))

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
        self.hide_focus_check.setChecked(s.ui.hide_on_focus_loss)
        self.bilingual_layout_combo.setCurrentIndex(
            self.bilingual_layout_combo.findData(s.ui.bilingual_layout)
        )

        # OCR
        ocr_index = self.ocr_lang_combo.findData(s.ocr.language)
        if ocr_index >= 0:
            self.ocr_lang_combo.setCurrentIndex(ocr_index)
        self.enhance_image_check.setChecked(s.ocr.enhance_image)
        self.ocr_review_check.setChecked(s.ocr.review_before_translation)

        # Privacy
        self.allow_content_logging_check.setChecked(s.privacy.allow_content_logging)
        self.keep_ocr_captures_check.setChecked(s.privacy.keep_ocr_captures)
        self.speech_locale_combo.setCurrentIndex(
            self.speech_locale_combo.findData(s.speech.source_locale)
        )
        self.speech_rate_spin.setValue(s.speech.rate)
        self.source_voice_combo.clear()
        self.target_voice_combo.clear()
        self._update_speech_voice_choices()

        logger.debug("Settings loaded into UI")

    def _save_settings(self) -> None:
        """Save UI values to settings."""
        new_settings = self._build_settings_from_ui()
        if new_settings is None:
            return

        try:
            new_settings.save()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Settings Error",
                f"Could not save settings:\n\n{e}",
            )
            return

        self.settings = new_settings
        self.settings_changed.emit(new_settings)

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
        host = self._validated_host_from_input()
        if host is None:
            return

        self.connection_status.setText("Testing...")
        self.connection_status.setStyleSheet("color: gray;")
        self._set_network_buttons_enabled(False)

        task = self._network_tasks.start(
            "settings-connection-test",
            lambda task: self._connection_test_worker(task, host),
        )
        self._active_connection_task_id = task.task_id

    def _connection_test_worker(self, task: BackgroundTask, host: str) -> None:
        """Perform the actual connection test."""
        available = False
        message = "Not available"
        try:
            client = OllamaClient(host=host, read_timeout=3.0)
            available = client.is_available()
            message = "Connected" if available else "Not available"
        except Exception as e:
            message = str(e)

        if not task.is_cancelled():
            self.connection_test_finished.emit(task.task_id, available, message)

    def _on_connection_test_finished(
        self,
        task_id: int,
        available: bool,
        message: str,
    ) -> None:
        """Handle connection test completion on the UI thread."""
        if task_id != self._active_connection_task_id:
            return

        self._active_connection_task_id = None
        if available:
            self.connection_status.setText("✓ Connected")
            self.connection_status.setStyleSheet("color: green;")
            self._refresh_models()
        else:
            self.connection_status.setText(f"✗ {message}")
            self.connection_status.setStyleSheet("color: red;")
            self._set_network_buttons_enabled(True)

    def _refresh_models(self) -> None:
        """Refresh the list of available models."""
        host = self._validated_host_from_input()
        if host is None:
            return

        self.connection_status.setText("Refreshing models...")
        self.connection_status.setStyleSheet("color: gray;")
        self._set_network_buttons_enabled(False)

        task = self._network_tasks.start(
            "settings-refresh-models",
            lambda task: self._refresh_models_worker(task, host),
        )
        self._active_models_task_id = task.task_id

    def _refresh_models_worker(self, task: BackgroundTask, host: str) -> None:
        """Fetch available models in the background."""
        try:
            client = OllamaClient(host=host, read_timeout=3.0)
            models = client.list_models()
            model_names = [model.name for model in models]
            if not task.is_cancelled():
                self.models_refresh_finished.emit(task.task_id, model_names, "")
        except OllamaError as e:
            if not task.is_cancelled():
                self.models_refresh_finished.emit(task.task_id, [], str(e))
        except Exception as e:
            if not task.is_cancelled():
                self.models_refresh_finished.emit(task.task_id, [], str(e))

    def _on_models_refresh_finished(
        self,
        task_id: int,
        model_names: object,
        error_message: str,
    ) -> None:
        """Handle model refresh completion on the UI thread."""
        if task_id != self._active_models_task_id:
            return

        self._active_models_task_id = None
        self._set_network_buttons_enabled(True)

        if error_message:
            self.connection_status.setText("✗ Model refresh failed")
            self.connection_status.setStyleSheet("color: red;")
            logger.warning(f"Failed to refresh models: {error_message}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to fetch models: {error_message}\n\nMake sure Ollama is running.",
            )
            return

        current_model = self.model_combo.currentText()
        self.model_combo.clear()

        for model_name in model_names:
            self.model_combo.addItem(model_name)

        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        elif current_model:
            self.model_combo.setEditText(current_model)
            self.connection_status.setText("Configured model missing; choose an installed model")
            return

        self.connection_status.setText(f"✓ {self.model_combo.count()} models")
        self.connection_status.setStyleSheet("color: green;")
        logger.debug(f"Refreshed models: {list(model_names)}")

    def _set_network_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable buttons that touch Ollama."""
        self.test_btn.setEnabled(enabled)
        self.refresh_models_btn.setEnabled(enabled)

    def _validated_host_from_input(self) -> Optional[str]:
        """Return a validated host from the UI, or show an error."""
        host = self.host_input.text().strip() or self.settings.ollama.host
        try:
            return OllamaSettings(
                host=host,
                model=self.model_combo.currentText().strip() or self.settings.ollama.model,
                general_model=self.settings.ollama.general_model,
            ).host
        except ValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid Ollama Host",
                self._format_validation_error(e),
            )
            return None

    def _build_settings_from_ui(self) -> Optional[AppSettings]:
        """Create a validated settings object from current UI values."""
        data = self.settings.model_dump()

        data["ollama"]["host"] = self.host_input.text().strip() or self.settings.ollama.host
        data["ollama"]["model"] = (
            self.model_combo.currentText().strip() or self.settings.ollama.model
        )
        data["ollama"].update(
            {
                "context_window": self.context_spin.value(),
                "max_output_tokens": self.output_spin.value(),
                "temperature": self.temperature_spin.value(),
                "thinking": self.thinking_combo.currentText(),
                "keep_alive": self.keep_alive_spin.value(),
                "read_timeout": self.timeout_spin.value(),
            }
        )

        data["translation"]["source_language"] = self.source_lang_combo.currentData()
        data["translation"]["target_language"] = self.target_lang_combo.currentData()
        data["translation"]["preset"] = self.preset_combo.currentText()
        data["translation"]["custom_prompt"] = (
            (self.custom_prompt_input.toPlainText().strip() or None)
            if self.custom_prompt_check.isChecked()
            else None
        )

        translate_hotkey = self.translate_hotkey_input.text().strip()
        if translate_hotkey:
            data["hotkeys"]["translate"] = translate_hotkey

        ocr_hotkey = self.ocr_hotkey_input.text().strip()
        if ocr_hotkey:
            data["hotkeys"]["ocr"] = ocr_hotkey

        data["ui"]["theme"] = self.theme_combo.currentText().lower()
        data["ui"]["font_size"] = self.font_size_spin.value()
        data["ui"]["popup_opacity"] = self.opacity_slider.value() / 100.0
        data["ui"]["show_source_text"] = self.show_source_check.isChecked()
        data["ui"]["hide_on_focus_loss"] = self.hide_focus_check.isChecked()
        data["ui"]["bilingual_layout"] = self.bilingual_layout_combo.currentData()

        data["ocr"]["language"] = self.ocr_lang_combo.currentData()
        data["ocr"]["enhance_image"] = self.enhance_image_check.isChecked()
        data["ocr"]["review_before_translation"] = self.ocr_review_check.isChecked()

        data["privacy"]["allow_content_logging"] = self.allow_content_logging_check.isChecked()
        data["privacy"]["keep_ocr_captures"] = self.keep_ocr_captures_check.isChecked()
        data["speech"] = {
            "source_locale": self.speech_locale_combo.currentData(),
            "source_voice": self.source_voice_combo.currentData() or "",
            "target_voice": self.target_voice_combo.currentData() or "",
            "rate": self.speech_rate_spin.value(),
        }

        try:
            return AppSettings.model_validate(data)
        except ValidationError as e:
            QMessageBox.warning(
                self,
                "Invalid Settings",
                self._format_validation_error(e),
            )
            return None

    def _format_validation_error(self, error: ValidationError) -> str:
        """Format validation errors for a compact user-facing dialog."""
        lines = []
        for item in error.errors():
            location = " > ".join(str(part) for part in item.get("loc", ()))
            message = item.get("msg", "Invalid value")
            lines.append(f"{location}: {message}" if location else message)
        return "\n".join(lines)

    def _cancel_network_tasks(self) -> None:
        self._active_connection_task_id = None
        self._active_models_task_id = None
        self._network_tasks.cancel_all()

    def done(self, result: int) -> None:
        """Save, Cancel and Escape also invalidate outstanding network results."""
        self._cancel_network_tasks()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cancel_network_tasks()
        super().closeEvent(event)
