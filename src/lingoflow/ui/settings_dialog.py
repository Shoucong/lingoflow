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
from lingoflow.core.translation_profiles import is_milmmt_model
from lingoflow.infrastructure.macos.speech import MacOSSpeechService
from lingoflow.infrastructure.ollama_client import OllamaClient, OllamaError
from lingoflow.infrastructure.tasks import BackgroundTask, TaskRunner
from lingoflow.ui.languages import language_name
from lingoflow.ui.theme import apply_palette
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class SettingsDialog(QDialog):
    """
    Settings configuration dialog.

    Organized into tabs:
    - 通用: languages, hotkeys, OCR and reading-window preferences
    - 朗读: voices and speaking rate
    - 模型与高级: Ollama connection, model parameters, prompts and diagnostics

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
        self.model_combo.currentTextChanged.connect(self._update_model_controls)
        self.custom_prompt_check.toggled.connect(self._update_model_controls)
        apply_palette(self, self.settings.ui.theme)
        self._speech.voices_changed.connect(self._update_speech_voice_choices)
        self.speech_locale_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.source_lang_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.target_lang_combo.currentIndexChanged.connect(self._update_speech_voice_choices)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.theme_combo.currentIndexChanged.connect(self._preview_theme)
        self.connection_test_finished.connect(self._on_connection_test_finished)
        self.models_refresh_finished.connect(self._on_models_refresh_finished)

        logger.debug("SettingsDialog initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure dialog window."""
        self.setWindowTitle("LingoFlow 设置")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.resize(600, 620)
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)

    def _setup_ui(self) -> None:
        """Build the UI: everyday preferences first, connection and model tuning last."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._general_tab = self._add_scroll_tab(self._create_general_tab(), "通用")
        self._speech_tab = self._add_scroll_tab(self._create_speech_tab(), "朗读")
        self._advanced_tab = self._add_scroll_tab(self._create_advanced_tab(), "模型与高级")

        button_layout = QHBoxLayout()
        self.reset_btn = QPushButton("恢复默认设置")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(self.reset_btn)
        button_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("保存")
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

    def show_section(self, section: str) -> None:
        """Open a named section, e.g. "speech" from the reading window."""
        page = {
            "general": self._general_tab,
            "speech": self._speech_tab,
            "advanced": self._advanced_tab,
        }.get(section)
        if page is not None:
            self.tabs.setCurrentWidget(page)

    def _preview_theme(self, *_args) -> None:
        apply_palette(self, self.theme_combo.currentData() or "system")

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: gray; font-size: 11px;")
        return label

    # =============================================================================
    # Tab Creation
    # =============================================================================

    def _create_general_tab(self) -> QWidget:
        """Everyday preferences: languages, hotkeys, OCR and the reading window."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        lang_group = QGroupBox("翻译")
        lang_layout = QFormLayout(lang_group)
        self.source_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            self.source_lang_combo.addItem(
                "自动识别" if lang == "auto" else language_name(lang), lang
            )
        self.source_lang_combo.setToolTip(
            "MiLMMT 在本机识别原文语言，单个拉丁字母单词按英语处理。"
            "短文本识别不准时可在这里指定。"
        )
        lang_layout.addRow("原文语言：", self.source_lang_combo)
        self.target_lang_combo = QComboBox()
        for lang in SUPPORTED_LANGUAGES:
            if lang != "auto":
                self.target_lang_combo.addItem(language_name(lang), lang)
        lang_layout.addRow("译文语言：", self.target_lang_combo)
        layout.addWidget(lang_group)

        hotkeys_group = QGroupBox("快捷键")
        hotkeys_layout = QFormLayout(hotkeys_group)
        self.translate_hotkey_input = QLineEdit()
        self.translate_hotkey_input.setPlaceholderText("<alt>+d")
        hotkeys_layout.addRow("翻译选中文字：", self.translate_hotkey_input)
        self.ocr_hotkey_input = QLineEdit()
        self.ocr_hotkey_input.setPlaceholderText("<alt>+s")
        hotkeys_layout.addRow("截图识别翻译：", self.ocr_hotkey_input)
        hotkeys_layout.addRow(
            self._note(
                "格式如 <alt>+d、<cmd>+<shift>+t。修饰键：<alt>（Option）、<ctrl>、<cmd>、<shift>。"
            )
        )
        layout.addWidget(hotkeys_group)

        ocr_group = QGroupBox("截图识别")
        ocr_layout = QFormLayout(ocr_group)
        self.ocr_lang_combo = QComboBox()
        for display, code in [
            ("英语", "eng"),
            ("简体中文", "chi_sim"),
            ("繁体中文", "chi_tra"),
            ("日语", "jpn"),
            ("韩语", "kor"),
            ("英语 + 中文", "eng+chi_sim"),
            ("英语 + 日语", "eng+jpn"),
        ]:
            self.ocr_lang_combo.addItem(display, code)
        ocr_layout.addRow("图片中的文字：", self.ocr_lang_combo)
        self.enhance_image_check = QCheckBox("识别前增强图片")
        self.enhance_image_check.setToolTip("提高对比度并锐化，改善识别效果")
        ocr_layout.addRow("", self.enhance_image_check)
        self.ocr_review_check = QCheckBox("翻译前先校对识别结果")
        ocr_layout.addRow("", self.ocr_review_check)
        layout.addWidget(ocr_group)

        popup_group = QGroupBox("阅读窗口")
        popup_layout = QFormLayout(popup_group)
        self.theme_combo = QComboBox()
        for display, value in [("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")]:
            self.theme_combo.addItem(display, value)
        popup_layout.addRow("外观：", self.theme_combo)

        font_size_layout = QHBoxLayout()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 24)
        self.font_size_spin.setSuffix(" px")
        font_size_layout.addWidget(self.font_size_spin)
        font_size_layout.addStretch()
        popup_layout.addRow("字号：", font_size_layout)

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
        popup_layout.addRow("不透明度：", opacity_layout)

        self.show_source_check = QCheckBox("显示原文摘要")
        popup_layout.addRow("", self.show_source_check)
        self.bilingual_layout_combo = QComboBox()
        self.bilingual_layout_combo.addItem("原文在上，译文在下", "stacked")
        self.bilingual_layout_combo.addItem("原文与译文并排", "side_by_side")
        popup_layout.addRow("排列：", self.bilingual_layout_combo)
        popup_layout.addRow(
            self._note(
                "未固定的翻译窗口在点击或切换到其他应用时自动收起；"
                "点击窗口右上角的图钉即可让它保持显示。"
            )
        )
        layout.addWidget(popup_group)
        layout.addStretch()
        return tab

    def _create_speech_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.speech_locale_combo = QComboBox()
        self.speech_locale_combo.addItem("英语（美国）", "en-US")
        self.speech_locale_combo.addItem("英语（英国）", "en-GB")
        for language, locale in LANGUAGE_LOCALES.items():
            if language != "English":
                self.speech_locale_combo.addItem(language_name(language), locale)
        layout.addRow("自动识别时的原文口音：", self.speech_locale_combo)
        self.source_voice_combo = QComboBox()
        self.target_voice_combo = QComboBox()
        layout.addRow("原文音色：", self.source_voice_combo)
        layout.addRow("译文音色：", self.target_voice_combo)
        self.speech_rate_spin = QSpinBox()
        self.speech_rate_spin.setRange(80, 300)
        self.speech_rate_spin.setSuffix(" 词/分钟")
        layout.addRow("语速：", self.speech_rate_spin)
        refresh = QPushButton("刷新已安装的音色")
        refresh.clicked.connect(self._speech.refresh_voices)
        layout.addRow(refresh)
        layout.addRow(
            self._note(
                "使用本机已下载的 macOS 语音，离线可用。更多音色可在“系统设置 → 辅助功能 → "
                "朗读内容”中下载。原文与译文分别使用各自的音色。"
            )
        )
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
            combo.addItem("自动选择", "")
            for voice in self._speech.voices:
                if voice.locale == locale:
                    combo.addItem(voice.name, voice.name)
            if current and combo.findData(current) < 0:
                combo.addItem(f"{current}（当前语言不可用）", current)
            combo.setCurrentIndex(max(0, combo.findData(current)))

    def _create_advanced_tab(self) -> QWidget:
        """Connection, model parameters, prompts and troubleshooting."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        ollama_group = QGroupBox("Ollama 连接与模型")
        ollama_layout = QFormLayout(ollama_group)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("http://localhost:11434")
        ollama_layout.addRow("地址：", self.host_input)
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        test_layout.addWidget(self.test_btn)
        self.connection_status = QLabel("")
        test_layout.addWidget(self.connection_status)
        test_layout.addStretch()
        ollama_layout.addRow("", test_layout)
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(240)
        model_layout.addWidget(self.model_combo, 1)
        self.refresh_models_btn = QPushButton("刷新")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.refresh_models_btn)
        ollama_layout.addRow("翻译模型：", model_layout)
        layout.addWidget(ollama_group)

        generation = QGroupBox("模型参数")
        form = QFormLayout(generation)
        self.context_spin = QSpinBox()
        self.context_spin.setRange(2048, 131072)
        self.context_spin.setSingleStep(1024)
        form.addRow("上下文窗口（token）：", self.context_spin)
        self.output_spin = QSpinBox()
        self.output_spin.setRange(128, 32768)
        self.output_spin.setSingleStep(256)
        form.addRow("每段输出上限（token）：", self.output_spin)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.05)
        form.addRow("温度：", self.temperature_spin)
        self.thinking_combo = QComboBox()
        for display, value in [("关闭", "off"), ("自动", "auto"), ("开启", "on")]:
            self.thinking_combo.addItem(display, value)
        form.addRow("思考（支持的模型）：", self.thinking_combo)
        self.keep_alive_spin = QSpinBox()
        self.keep_alive_spin.setRange(0, 3600)
        self.keep_alive_spin.setSuffix(" 秒")
        form.addRow("模型保持加载：", self.keep_alive_spin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("生成读取超时：", self.timeout_spin)
        self.model_profile_note = self._note(
            "MiLMMT 使用官方推荐的翻译格式和确定性解码；温度、思考、翻译风格和自定义提示词"
            "仅对其他模型生效。"
        )
        form.addRow(self.model_profile_note)
        layout.addWidget(generation)

        style_group = QGroupBox("翻译风格（其他模型）")
        style_layout = QFormLayout(style_group)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("忠实", "faithful")
        self.preset_combo.addItem("学术", "academic")
        style_layout.addRow("风格：", self.preset_combo)
        self.custom_prompt_check = QCheckBox("使用自定义系统提示词")
        style_layout.addRow("", self.custom_prompt_check)
        self.custom_prompt_input = QTextEdit()
        self.custom_prompt_input.setAcceptRichText(False)
        self.custom_prompt_input.setMaximumHeight(120)
        self.custom_prompt_check.toggled.connect(self.custom_prompt_input.setEnabled)
        style_layout.addRow(self.custom_prompt_input)
        layout.addWidget(style_group)

        privacy_group = QGroupBox("隐私与诊断")
        privacy_layout = QFormLayout(privacy_group)
        self.allow_content_logging_check = QCheckBox("在日志中记录选中文字和识别文字")
        self.allow_content_logging_check.setToolTip("默认关闭。仅在排查问题时临时开启，日志可能包含私人内容。")
        privacy_layout.addRow("", self.allow_content_logging_check)
        self.keep_ocr_captures_check = QCheckBox("保留截图文件用于排查")
        self.keep_ocr_captures_check.setToolTip("默认关闭。关闭时识别完成后会删除截图。")
        privacy_layout.addRow("", self.keep_ocr_captures_check)
        privacy_layout.addRow(
            self._note("日常使用请保持两项关闭，阅读内容不会写入日志，临时截图会被清理。")
        )
        layout.addWidget(privacy_group)
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
        self.thinking_combo.setCurrentIndex(max(0, self.thinking_combo.findData(s.ollama.thinking)))
        self.keep_alive_spin.setValue(s.ollama.keep_alive)
        self.timeout_spin.setValue(int(s.ollama.read_timeout))

        # Translation
        source_index = self.source_lang_combo.findData(s.translation.source_language)
        if source_index >= 0:
            self.source_lang_combo.setCurrentIndex(source_index)

        target_index = self.target_lang_combo.findData(s.translation.target_language)
        if target_index >= 0:
            self.target_lang_combo.setCurrentIndex(target_index)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(s.translation.preset)))
        self.custom_prompt_check.setChecked(bool(s.translation.custom_prompt))
        self.custom_prompt_input.setPlainText(s.translation.custom_prompt or "")
        self.custom_prompt_input.setEnabled(bool(s.translation.custom_prompt))

        # Hotkeys
        self.translate_hotkey_input.setText(s.hotkeys.translate)
        self.ocr_hotkey_input.setText(s.hotkeys.ocr)

        # Appearance
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(s.ui.theme)))

        self.font_size_spin.setValue(s.ui.font_size)
        self.opacity_slider.setValue(int(s.ui.popup_opacity * 100))
        self.show_source_check.setChecked(s.ui.show_source_text)
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
        self._update_model_controls()

        logger.debug("Settings loaded into UI")

    def _update_model_controls(self, *_args) -> None:
        fixed = is_milmmt_model(self.model_combo.currentText())
        for widget in (
            self.temperature_spin,
            self.thinking_combo,
            self.preset_combo,
            self.custom_prompt_check,
        ):
            widget.setEnabled(not fixed)
        self.custom_prompt_input.setEnabled(not fixed and self.custom_prompt_check.isChecked())
        self.model_profile_note.setVisible(fixed)
        if fixed:
            self.temperature_spin.setValue(0)
            self.thinking_combo.setCurrentIndex(self.thinking_combo.findData("off"))

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
                "无法保存设置",
                f"保存设置时出错：\n\n{e}",
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
            "恢复默认设置",
            "确定要把所有设置恢复为默认值吗？保存后生效。",
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

        self.connection_status.setText("正在测试…")
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
        message = "无法连接"
        try:
            client = OllamaClient(host=host, read_timeout=3.0)
            available = client.is_available()
            message = "已连接" if available else "无法连接"
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
            self.connection_status.setText("✓ 已连接")
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

        self.connection_status.setText("正在获取模型列表…")
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
            self.connection_status.setText("✗ 获取模型列表失败")
            self.connection_status.setStyleSheet("color: red;")
            logger.warning(f"Failed to refresh models: {error_message}")
            QMessageBox.warning(
                self,
                "无法获取模型",
                f"获取模型列表失败：{error_message}\n\n请确认 Ollama 正在运行。",
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
            self.connection_status.setText("当前模型未安装，请选择已安装的模型")
            return

        self.connection_status.setText(f"✓ {self.model_combo.count()} 个模型")
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
                "Ollama 地址无效",
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
                "thinking": self.thinking_combo.currentData(),
                "keep_alive": self.keep_alive_spin.value(),
                "read_timeout": self.timeout_spin.value(),
            }
        )

        data["translation"]["source_language"] = self.source_lang_combo.currentData()
        data["translation"]["target_language"] = self.target_lang_combo.currentData()
        data["translation"]["preset"] = self.preset_combo.currentData()
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

        data["ui"]["theme"] = self.theme_combo.currentData()
        data["ui"]["font_size"] = self.font_size_spin.value()
        data["ui"]["popup_opacity"] = self.opacity_slider.value() / 100.0
        data["ui"]["show_source_text"] = self.show_source_check.isChecked()
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
                "设置无效",
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
