"""
Translation popup window for LingoFlow.

A reading window: the translation takes the main space, the source is a short
read-only excerpt that can be expanded, and actions appear only when they apply.
Editing the source (typed input, OCR review, "编辑原文") is an explicit mode with
its own Translate/Cancel path and the retention rules of a normal window.

Window policy has one source of truth, :meth:`_auto_dismiss_allowed`: an
unpinned reading window closes when the user clicks another application or
switches to one, whatever the translation state. Pinned and editing windows stay.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lingoflow.config.constants import (
    POPUP_MIN_HEIGHT,
    POPUP_MIN_WIDTH,
    SUPPORTED_LANGUAGES,
)
from lingoflow.config.settings import AppSettings
from lingoflow.core.speech import LANGUAGE_LOCALES, SpeechRequest
from lingoflow.infrastructure.macos.event_monitor import OutsideInteractionMonitor
from lingoflow.infrastructure.macos.speech import MacOSSpeechService
from lingoflow.ui import icons
from lingoflow.ui.languages import language_name
from lingoflow.ui.theme import apply_palette, colors
from lingoflow.ui.translation_view import TranslationView
from lingoflow.ui.window_controller import PopupWindowController
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

SOURCE_PREVIEW_LINES = 3
EDIT_HEIGHT = 320


class PopupMode(Enum):
    READING = "reading"
    EDITING = "editing"


# =============================================================================
# Signal Bridge for Thread-Safe UI Updates
# =============================================================================


class TranslationSignals(QObject):
    """Signals for thread-safe communication with the popup."""

    chunk_received = pyqtSignal(str)  # New text chunk
    translation_started = pyqtSignal()  # Translation began
    translation_finished = pyqtSignal()  # Translation complete
    translation_error = pyqtSignal(str)  # Error message
    translation_cleared = pyqtSignal()  # Clear translation output


def _tool_button(name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName(name)
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setIconSize(QSize(16, 16))
    button.setFixedSize(26, 26)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    return button


def _text_button(name: str, text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


# =============================================================================
# Translation Popup Window
# =============================================================================


class TranslationPopup(QWidget):
    """Popup window for reading streamed translations."""

    language_changed = pyqtSignal(str)
    closed = pyqtSignal()
    outside_clicked = pyqtSignal()
    stop_requested = pyqtSignal()
    retry_requested = pyqtSignal(str)
    settings_requested = pyqtSignal(str)
    pinned_changed = pyqtSignal(bool)

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        window_state_path: Path | None = None,
        speech_service: MacOSSpeechService | None = None,
    ):
        super().__init__()

        self.settings = settings or AppSettings.load()
        self.signals = TranslationSignals()
        self.speech = speech_service or MacOSSpeechService.shared()
        self._speech_owner = uuid4().hex

        self._source_text = ""
        self._translated_text = ""
        self._detected_source: str | None = None
        self._is_translating = False
        self._state = "idle"  # idle, waiting, streaming, done, stopped, failed
        self._progress = (0, 0)
        self._mode = PopupMode.READING
        self._edit_origin = "input"  # "input" (typed/OCR) or "reading"
        self._edit_start_text = ""
        self._source_expanded = False
        self._source_visible = self.settings.ui.show_source_text
        self._side_by_side = self.settings.ui.bilingual_layout == "side_by_side"
        self._suppress_language_signal = False
        self._dismiss_emitted = False
        self._closing = False
        self._native_monitor = OutsideInteractionMonitor()
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(self._clear_transient_status)
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._refresh_icons)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_to_content)

        self._setup_window()
        self._setup_ui()
        self.window_controller = PopupWindowController(self, window_state_path)
        self._connect_signals()
        self._refresh_theme()
        self._apply_pin_state()
        self._update_actions()
        self._update_more_menu()

        logger.debug("TranslationPopup initialized")

    # =============================================================================
    # Setup
    # =============================================================================

    def _setup_window(self) -> None:
        # Native decorations provide reliable dragging, edge/corner resizing and close.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowTitle("LingoFlow")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(POPUP_MIN_WIDTH)
        self.setMinimumHeight(POPUP_MIN_HEIGHT)
        self.resize(460, 260)

    def _setup_ui(self) -> None:
        self.container = QFrame(self)
        self.container.setObjectName("popupContainer")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 8, 10, 8)
        layout.setSpacing(6)

        # --- Header: languages on the left, pin and more on the right ---
        header = QHBoxLayout()
        header.setSpacing(6)
        self.mode_label = QLabel("编辑原文")
        self.mode_label.setObjectName("modeLabel")
        header.addWidget(self.mode_label)
        self.source_label = QLabel(self._format_source_language())
        self.source_label.setObjectName("sourceLabel")
        header.addWidget(self.source_label)
        self.arrow_label = QLabel("→")
        self.arrow_label.setObjectName("arrowLabel")
        header.addWidget(self.arrow_label)
        self.target_combo = QComboBox()
        self.target_combo.setObjectName("targetCombo")
        self.target_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.target_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.target_combo.setToolTip("译文语言")
        for lang in SUPPORTED_LANGUAGES:
            if lang != "auto":
                self.target_combo.addItem(language_name(lang), lang)
        index = self.target_combo.findData(self.settings.translation.target_language)
        if index >= 0:
            self.target_combo.setCurrentIndex(index)
        header.addWidget(self.target_combo)
        header.addStretch()

        self.pin_btn = _tool_button("pinButton", "")
        self.pin_btn.setCheckable(True)
        header.addWidget(self.pin_btn)

        self.more_btn = _tool_button("moreButton", "更多操作")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_btn)
        self.edit_action = self.more_menu.addAction("编辑原文")
        self.edit_action.triggered.connect(self.enter_edit_mode)
        self.more_menu.addSeparator()
        self.copy_source_action = self.more_menu.addAction("复制原文")
        self.copy_source_action.triggered.connect(self._copy_source)
        self.copy_both_action = self.more_menu.addAction("复制原文和译文")
        self.copy_both_action.triggered.connect(self._copy_bilingual)
        self.more_menu.addSeparator()
        self.show_source_action = self.more_menu.addAction("显示原文")
        self.show_source_action.setCheckable(True)
        self.show_source_action.toggled.connect(self._set_source_visible)
        self.side_by_side_action = self.more_menu.addAction("原文与译文并排")
        self.side_by_side_action.setCheckable(True)
        self.side_by_side_action.toggled.connect(self._set_side_by_side)
        self.more_menu.addSeparator()
        self.speech_settings_action = self.more_menu.addAction("朗读与音色设置…")
        self.speech_settings_action.triggered.connect(
            lambda: self.settings_requested.emit("speech")
        )
        self.more_menu.aboutToShow.connect(self._update_more_menu)
        self.more_btn.setMenu(self.more_menu)
        # A plain QToolButton menu shows an arrow indicator; the icon is enough here.
        self.more_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        header.addWidget(self.more_btn)
        layout.addLayout(header)

        # --- Body: source excerpt and translation ---
        self.text_splitter = TranslationView()
        self.source_text = self.text_splitter.source
        self.translation_text = self.text_splitter.target
        self.source_text.setPlaceholderText("输入或粘贴要翻译的文字")

        self.speak_source_btn = _tool_button("speakSourceButton", "")
        self.speak_source_btn.clicked.connect(self._speak_source)
        self.text_splitter.source_tools.addWidget(self.speak_source_btn)
        self.text_splitter.source_tools.addStretch()

        self.expand_source_btn = QPushButton("展开原文")
        self.expand_source_btn.setObjectName("linkButton")
        self.expand_source_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.expand_source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_source_btn.clicked.connect(self._toggle_source_expanded)
        self.text_splitter.source_footer.addWidget(self.expand_source_btn)
        self.text_splitter.source_footer.addStretch()
        layout.addWidget(self.text_splitter, 1)

        # --- Footer: state-dependent actions ---
        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.status_label, 1)

        self.stop_btn = _text_button("stopButton", "停止")
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        footer.addWidget(self.stop_btn)
        self.retry_btn = _text_button("retryButton", "重试")
        self.retry_btn.clicked.connect(self._on_retry_clicked)
        footer.addWidget(self.retry_btn)
        self.latest_btn = _text_button("latestButton", "回到末尾")
        self.latest_btn.setToolTip("取消选择并跟随新的译文")
        self.latest_btn.clicked.connect(self._scroll_to_latest)
        footer.addWidget(self.latest_btn)
        self.cancel_edit_btn = _text_button("cancelEditButton", "取消")
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        footer.addWidget(self.cancel_edit_btn)
        self.translate_btn = _text_button("primaryButton", "翻译")
        self.translate_btn.setToolTip("翻译编辑后的原文（⌘↵）")
        self.translate_btn.clicked.connect(self._on_retry_clicked)
        footer.addWidget(self.translate_btn)

        self.copy_btn = _tool_button("copyButton", "复制译文")
        self.copy_btn.clicked.connect(self._copy_translation)
        footer.addWidget(self.copy_btn)
        self.speak_translation_btn = _tool_button("speakTranslationButton", "")
        self.speak_translation_btn.clicked.connect(self._speak_translation)
        footer.addWidget(self.speak_translation_btn)
        layout.addLayout(footer)

    def _connect_signals(self) -> None:
        self.signals.chunk_received.connect(self._on_chunk_received)
        self.signals.translation_started.connect(self._on_translation_started)
        self.signals.translation_finished.connect(self._on_translation_finished)
        self.signals.translation_error.connect(self._on_translation_error)
        self.signals.translation_cleared.connect(self._on_translation_cleared)

        self.target_combo.currentIndexChanged.connect(self._on_language_changed)
        self.outside_clicked.connect(self._dismiss_from_outside)
        self.pin_btn.toggled.connect(self._set_pinned)
        scrollbar = self.translation_text.verticalScrollBar()
        scrollbar.valueChanged.connect(self._update_latest_button)
        scrollbar.rangeChanged.connect(self._update_latest_button)
        # Large inserts are laid out incrementally; a new scroll range means more to show.
        scrollbar.rangeChanged.connect(lambda *_: self._schedule_fit())
        self.translation_text.selectionChanged.connect(self._update_latest_button)
        self.speech.state_changed.connect(self._update_actions)
        self.speech.failed.connect(self._speech_failed)
        self.source_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.source_text.customContextMenuRequested.connect(self._source_context_menu)
        self.translation_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.translation_text.customContextMenuRequested.connect(self._translation_context_menu)
        self.source_text.textChanged.connect(self._source_edited)
        self.source_text.document().documentLayout().documentSizeChanged.connect(
            self._source_layout_changed
        )
        self.translation_text.document().documentLayout().documentSizeChanged.connect(
            lambda *_: self._schedule_fit()
        )
        self._retry_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._retry_shortcut.activated.connect(self._on_submit_shortcut)
        QApplication.styleHints().colorSchemeChanged.connect(self._refresh_theme)

    # =============================================================================
    # Appearance
    # =============================================================================

    def _get_stylesheet(self) -> str:
        theme = colors(self.settings.ui.theme)
        font = self.settings.ui.font_size
        small = max(11, font - 2)
        return f"""
            #popupContainer {{ background: {theme['background']}; color: {theme['text']}; }}
            QLabel {{ color: {theme['muted']}; font-size: {small}px; }}
            #modeLabel {{ color: {theme['text']}; font-weight: 600; font-size: {small}px; }}
            #sourceLabel, #arrowLabel {{ color: {theme['muted']}; }}
            QTextEdit {{ background: transparent; color: {theme['text']}; border: none;
                padding: 0px; font-size: {font}px;
                selection-background-color: {theme['selection']}; }}
            #sourceText {{ color: {theme['source']}; font-size: {max(11, font - 1)}px; }}
            #sourceText[editing="true"] {{ background: {theme['input']}; color: {theme['text']};
                border: 1px solid {theme['border']}; border-radius: 6px; padding: 6px;
                font-size: {font}px; }}
            QComboBox#targetCombo {{ background: transparent; color: {theme['text']};
                border: none; border-radius: 5px; padding: 2px 4px; font-size: {small}px; }}
            QComboBox#targetCombo:hover {{ background: {theme['hover']}; }}
            QComboBox#targetCombo::drop-down {{ border: none; width: 12px; }}
            QComboBox QAbstractItemView, QMenu {{ background: {theme['control']};
                color: {theme['text']}; selection-background-color: {theme['accent']};
                selection-color: {theme['on_accent']}; }}
            QToolButton {{ background: transparent; border: none; border-radius: 6px; }}
            QToolButton:hover {{ background: {theme['hover']}; }}
            QToolButton#pinButton:checked {{ background: {theme['accent_soft']}; }}
            QPushButton {{ background: transparent; color: {theme['text']};
                border: 1px solid {theme['border']}; border-radius: 6px; padding: 3px 10px;
                font-size: {small}px; }}
            QPushButton:hover {{ background: {theme['hover']}; }}
            QPushButton#primaryButton {{ background: {theme['accent']};
                color: {theme['on_accent']}; border-color: {theme['accent']}; }}
            QPushButton#linkButton {{ border: none; padding: 0px; color: {theme['accent']};
                font-size: {small}px; }}
            QPushButton#linkButton:hover {{ background: transparent; text-decoration: underline; }}
            #statusLabel[error="true"] {{ color: {theme['danger']}; }}
            QSplitter::handle {{ background: transparent; }}
            QSplitter::handle:vertical {{ border-top: 1px solid {theme['border']};
                margin: 4px 0px; }}
            QSplitter::handle:horizontal {{ border-left: 1px solid {theme['border']};
                margin: 0px 4px; }}
        """

    def _refresh_theme(self, *_args) -> None:
        apply_palette(self, self.settings.ui.theme)
        self.container.setStyleSheet(self._get_stylesheet())
        self.setWindowOpacity(self.settings.ui.popup_opacity)
        self._apply_layout_orientation()
        self._refresh_icons()
        self._update_source_preview()

    def _ink(self, key: str = "muted") -> str:
        return colors(self.settings.ui.theme)[key]

    def _refresh_icons(self) -> None:
        pinned = self.window_controller.pinned if hasattr(self, "window_controller") else False
        self.pin_btn.setIcon(
            icons.pin_icon(self._ink("accent") if pinned else self._ink("muted"), filled=pinned)
        )
        self.more_btn.setIcon(icons.more_icon(self._ink()))
        copied = self._copy_feedback_timer.isActive()
        self.copy_btn.setIcon(
            icons.check_icon(self._ink("accent")) if copied else icons.copy_icon(self._ink())
        )
        self.latest_btn.setIcon(icons.arrow_down_icon(self._ink("text")))
        for button, kind in (
            (self.speak_source_btn, "source"),
            (self.speak_translation_btn, "translation"),
        ):
            active = self.speech.is_active(self._speech_owner, kind)
            button.setIcon(
                icons.stop_icon(self._ink("accent")) if active else icons.speaker_icon(self._ink())
            )

    def _apply_layout_orientation(self) -> None:
        side = self._side_by_side and self._mode == PopupMode.READING
        orientation = Qt.Orientation.Horizontal if side else Qt.Orientation.Vertical
        if self.text_splitter.orientation() != orientation:
            self.text_splitter.setOrientation(orientation)
            if side:
                self.text_splitter.setSizes([1, 1])
        self._update_source_preview()

    # =============================================================================
    # Public Methods
    # =============================================================================

    def show_with_text(
        self,
        source_text: str,
        target_language: Optional[str] = None,
        source_language: Optional[str] = None,
    ) -> None:
        """Show the popup with source text and prepare for translation.

        A visible popup keeps its pin state and geometry and only replaces content.
        """
        self.speech.stop(self._speech_owner)
        self._source_text = source_text
        self._translated_text = ""
        self._detected_source = None
        self._state = "idle"
        self._progress = (0, 0)
        self._dismiss_emitted = False
        self._closing = False
        self._status_clear_timer.stop()
        self._source_expanded = False
        self._set_mode(PopupMode.READING)

        self.source_text.blockSignals(True)
        self.source_text.setPlainText(source_text)
        self.source_text.blockSignals(False)
        self.source_label.setText(self._format_source_language(source_language))
        self.source_label.setToolTip("")
        self.translation_text.clear()
        self.translation_text.setPlaceholderText("")
        self._set_status("")

        if target_language:
            self._set_target_language(target_language)

        self.window_controller.prepare_show(self._desired_height())
        self.show()
        self.raise_()
        self._start_outside_click_monitor()
        self._update_actions()
        self._schedule_fit()

        if self.settings.privacy.allow_content_logging:
            logger.debug(f"Popup shown with text: {source_text[:80]}...")
        else:
            logger.debug(f"Popup shown with source text ({len(source_text)} chars)")

    def append_translation(self, chunk: str) -> None:
        """Append a translation chunk (thread-safe)."""
        self.signals.chunk_received.emit(chunk)

    def start_translation(self) -> None:
        """Signal that translation has started (thread-safe)."""
        self.signals.translation_started.emit()

    def finish_translation(self) -> None:
        """Signal that translation has finished (thread-safe)."""
        self.signals.translation_finished.emit()

    def show_error(self, message: str) -> None:
        """Show an error message (thread-safe)."""
        self.signals.translation_error.emit(message)

    def clear_translation(self) -> None:
        """Clear current translation output (thread-safe)."""
        self.signals.translation_cleared.emit()

    def get_target_language(self) -> str:
        return self.target_combo.currentData() or self.settings.translation.target_language

    def get_source_text(self) -> str:
        return self.source_text.toPlainText()

    @property
    def is_reviewing(self) -> bool:
        return self._mode == PopupMode.EDITING

    @property
    def is_pinned(self) -> bool:
        return self.window_controller.pinned

    def prepare_review(self) -> None:
        """Enter the edit mode used for typed input and OCR review."""
        self._is_translating = False
        self._state = "idle"
        self._edit_origin = "input"
        self._enter_editing()

    def enter_edit_mode(self) -> None:
        """Edit the source of a finished, stopped or failed translation."""
        if self._is_translating or self._mode == PopupMode.EDITING:
            return
        self._edit_origin = "reading"
        self._enter_editing()

    def set_detected_source_language(self, language: str) -> None:
        """Show the language identified locally, instead of a generic "自动"."""
        self._detected_source = language
        self.source_label.setText(language_name(language))
        self.source_label.setToolTip("本机自动识别的原文语言")

    def update_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self._source_visible = settings.ui.show_source_text
        self._side_by_side = settings.ui.bilingual_layout == "side_by_side"
        self._refresh_theme()
        self._set_target_language(settings.translation.target_language)
        if not self._detected_source:
            self.source_label.setText(self._format_source_language())
        self._update_actions()
        self._update_more_menu()
        self._schedule_fit()

    def set_progress(self, completed: int, total: int) -> None:
        self._progress = (completed, total)
        if self._is_translating and total > 1:
            self._set_status(f"正在翻译 · 第 {min(completed + 1, total)}/{total} 段")

    def stop_translation(self) -> None:
        """Keep useful partial text without labeling it a completed translation."""
        self._is_translating = False
        self._state = "stopped"
        self._set_status("已停止 · 已保留部分译文" if self._translated_text else "已停止")
        self._update_actions()

    def dismiss(self) -> None:
        """Close as an interaction that ends this window (no confirmation)."""
        self._closing = True
        self.close()

    # =============================================================================
    # Translation state
    # =============================================================================

    def _on_chunk_received(self, chunk: str) -> None:
        if not chunk:
            return
        first = not self._translated_text
        self.text_splitter.append_output(chunk)
        self._translated_text += chunk
        if self._state == "waiting":
            self._state = "streaming"
            if self._progress[1] <= 1:
                self._set_status("正在翻译…")
        if first:
            self._update_actions()

    def _on_translation_started(self) -> None:
        self._source_text = self.get_source_text()
        self._is_translating = True
        self._state = "waiting"
        self._progress = (0, 0)
        self._status_clear_timer.stop()
        self._set_mode(PopupMode.READING)
        self._set_status("正在等待模型…")
        self.translation_text.setPlaceholderText("")
        self.speech.stop(self._speech_owner)
        self._update_actions()

    def _on_translation_finished(self) -> None:
        self._is_translating = False
        self._state = "done"
        self._set_status("")
        self._update_actions()

    def _on_translation_error(self, message: str) -> None:
        self._is_translating = False
        self._state = "failed"
        self._status_clear_timer.stop()
        self._set_status(
            "翻译失败 · 已保留部分译文" if self._translated_text else "翻译失败", error=True
        )
        self.status_label.setToolTip(message)
        self.translation_text.setPlaceholderText(message)
        self._update_actions()

    def _on_translation_cleared(self) -> None:
        self._translated_text = ""
        self.translation_text.clear()
        if self._is_translating:
            self._state = "waiting"
            self._set_status("正在重试…")
        self._update_actions()

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()

    def _on_retry_clicked(self) -> None:
        text = self.get_source_text()
        if text.strip():
            self.retry_requested.emit(text)

    def _on_submit_shortcut(self) -> None:
        if self._mode == PopupMode.EDITING or self.retry_btn.isVisible():
            self._on_retry_clicked()

    def _on_language_changed(self, _index: int) -> None:
        language = self.get_target_language()
        logger.debug(f"Target language changed to: {language}")
        if self.isVisible() and self.get_source_text() and not self._suppress_language_signal:
            self.language_changed.emit(language)

    # =============================================================================
    # Modes and presentation state
    # =============================================================================

    def _enter_editing(self) -> None:
        self.speech.stop(self._speech_owner)
        self._status_clear_timer.stop()
        self._edit_start_text = self.get_source_text()
        self._set_mode(PopupMode.EDITING)
        self._set_status("⌘↵ 翻译")
        self.status_label.setToolTip("")
        self._update_actions()
        if self.isVisible() and not self.window_controller.user_sized:
            self.window_controller.fit_height(EDIT_HEIGHT)
        self.activateWindow()
        self.source_text.setFocus()
        cursor = self.source_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.source_text.setTextCursor(cursor)

    def _set_mode(self, mode: PopupMode) -> None:
        if mode == self._mode and self.source_text.isReadOnly() == (mode == PopupMode.READING):
            return
        self._mode = mode
        editing = mode == PopupMode.EDITING
        self.source_text.setReadOnly(not editing)
        self.source_text.setProperty("editing", "true" if editing else "false")
        self.source_text.style().unpolish(self.source_text)
        self.source_text.style().polish(self.source_text)
        self.text_splitter.target_panel.setVisible(not editing)
        self.mode_label.setVisible(editing)
        self._apply_layout_orientation()
        self._update_actions()
        self._schedule_fit()

    def _cancel_edit(self) -> None:
        if not self._confirm_discard():
            return
        if self._edit_origin == "reading":
            self.source_text.blockSignals(True)
            self.source_text.setPlainText(self._source_text)
            self.source_text.blockSignals(False)
            self._set_mode(PopupMode.READING)
            self._set_status("")
            self._update_actions()
            self._schedule_fit()
        else:
            self.dismiss()

    def _edits_pending(self) -> bool:
        text = self.get_source_text()
        return (
            self._mode == PopupMode.EDITING
            and bool(text.strip())
            and text != self._edit_start_text
        )

    def _confirm_discard(self) -> bool:
        if not self._edits_pending():
            return True
        answer = QMessageBox.question(
            self,
            "放弃编辑？",
            "编辑过的原文还没有翻译，放弃后无法恢复。",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        if not error:
            self.status_label.setToolTip("")
        if self.status_label.property("error") != error:
            self.status_label.setProperty("error", error)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def _clear_transient_status(self) -> None:
        if self._state in {"done", "idle"} and self._mode == PopupMode.READING:
            self._set_status("")

    def _update_actions(self, *_args) -> None:
        """Show only the actions that apply to the current state."""
        editing = self._mode == PopupMode.EDITING
        reading = not editing
        has_source = bool(self.get_source_text().strip())
        has_output = bool(self._translated_text)
        ended = self._state in {"stopped", "failed"}

        self.mode_label.setVisible(editing)
        self.pin_btn.setVisible(reading)
        self.more_btn.setVisible(reading)
        self.text_splitter.source_panel.setVisible(editing or self._source_visible)
        self.speak_source_btn.setVisible(reading and has_source)
        self.stop_btn.setVisible(reading and self._is_translating)
        resumable = self._progress[0] > 0 and self._progress[1] > 1 and has_output
        self.retry_btn.setText("继续翻译" if resumable else "重试")
        self.retry_btn.setToolTip(
            "从未完成的段落继续（⌘↵）" if resumable else "重新翻译（⌘↵）"
        )
        self.retry_btn.setVisible(reading and ended and has_source)
        self.cancel_edit_btn.setVisible(editing)
        self.translate_btn.setVisible(editing)
        self.translate_btn.setEnabled(has_source)
        self.copy_btn.setVisible(reading and has_output)
        self.speak_translation_btn.setVisible(reading and has_output and not self._is_translating)
        self._update_latest_button()
        self._update_speech_tooltips()
        self._refresh_icons()

    def _update_speech_tooltips(self) -> None:
        for button, kind, name in (
            (self.speak_source_btn, "source", "原文"),
            (self.speak_translation_btn, "translation", "译文"),
        ):
            if self.speech.is_active(self._speech_owner, kind):
                tip = f"停止朗读{name}"
            else:
                tip = f"朗读{name}（有选中文字时只读选中部分）"
            button.setToolTip(tip)
            button.setAccessibleName(tip)

    def _update_more_menu(self) -> None:
        has_source = bool(self.get_source_text())
        self.edit_action.setEnabled(not self._is_translating)
        self.copy_source_action.setEnabled(has_source)
        self.copy_both_action.setEnabled(has_source and bool(self._translated_text))
        self.show_source_action.blockSignals(True)
        self.show_source_action.setChecked(self._source_visible)
        self.show_source_action.blockSignals(False)
        self.side_by_side_action.blockSignals(True)
        self.side_by_side_action.setChecked(self._side_by_side)
        self.side_by_side_action.blockSignals(False)

    def _set_source_visible(self, visible: bool) -> None:
        self._source_visible = visible
        self._update_actions()
        self._schedule_fit()

    def _set_side_by_side(self, enabled: bool) -> None:
        self._side_by_side = enabled
        self._apply_layout_orientation()
        self._schedule_fit()

    # =============================================================================
    # Source excerpt and automatic height
    # =============================================================================

    def _source_line_height(self) -> int:
        return self.source_text.fontMetrics().lineSpacing()

    def _source_document_height(self) -> int:
        document = self.source_text.document()
        return int(document.size().height() + 2 * self.source_text.frameWidth())

    def _collapsed_source_height(self) -> int:
        # Top document margin plus whole lines only, so no partial fourth line peeks out.
        margin = int(self.source_text.document().documentMargin())
        return self._source_line_height() * SOURCE_PREVIEW_LINES + margin + 1

    def _source_layout_changed(self, *_args) -> None:
        self._update_source_preview()
        self._schedule_fit()

    def _update_source_preview(self) -> None:
        """Collapse long sources to a short excerpt with an explicit expand control."""
        if not hasattr(self, "expand_source_btn"):
            return
        editing = self._mode == PopupMode.EDITING
        side = self.text_splitter.orientation() == Qt.Orientation.Horizontal
        content = self._source_document_height()
        collapsed = self._collapsed_source_height()
        overflow = content > collapsed + 2
        bar = Qt.ScrollBarPolicy
        if editing or side:
            self.source_text.setMinimumHeight(28)
            self.source_text.setMaximumHeight(16777215)
            self.source_text.setVerticalScrollBarPolicy(bar.ScrollBarAsNeeded)
            self.expand_source_btn.setVisible(False)
            return
        self.expand_source_btn.setVisible(overflow)
        self.expand_source_btn.setText("收起原文" if self._source_expanded else "展开原文")
        if self._source_expanded:
            limit = max(collapsed, int(self.window_controller.max_auto_height * 0.4))
            height = max(collapsed, min(content, limit))
            policy = bar.ScrollBarAsNeeded
        else:
            height = max(28, min(content, collapsed))
            policy = bar.ScrollBarAlwaysOff
            self.source_text.verticalScrollBar().setValue(0)
        # An exact height: the splitter otherwise gives the excerpt only its minimum.
        self.source_text.setVerticalScrollBarPolicy(policy)
        if self.source_text.height() != height or self.source_text.maximumHeight() != height:
            self.source_text.setFixedHeight(height)

    def _toggle_source_expanded(self) -> None:
        self._source_expanded = not self._source_expanded
        self._update_source_preview()
        self._schedule_fit()

    def _desired_height(self) -> int:
        """Window height that shows the whole translation, before the size limit."""
        if self._mode == PopupMode.EDITING:
            return EDIT_HEIGHT
        view = self.translation_text
        document = view.document()
        if document.textWidth() <= 0 or not self.isVisible():
            width = max(200, self.window_controller.preferred_width - 60)
            document.setTextWidth(width)
        content = int(document.size().height()) + 2 * view.frameWidth() + 4
        content = max(content, view.minimumHeight())
        extra = self.height() - view.height() if self.isVisible() else 0
        if extra <= 0:
            source = 0
            if self.text_splitter.source_panel.isVisibleTo(self):
                source = self.source_text.maximumHeight()
                source = min(source, self._source_document_height()) + 30
            extra = 90 + source
        return extra + content

    def _schedule_fit(self) -> None:
        if self.isVisible():
            self._fit_timer.start(0)

    def _fit_to_content(self) -> None:
        if self.text_splitter.orientation() == Qt.Orientation.Horizontal:
            return
        if self._mode == PopupMode.EDITING:
            return
        # While output streams in, only grow; a retry that clears text must not bounce.
        grow_only = self._state in {"waiting", "streaming"}
        self.window_controller.fit_height(self._desired_height(), grow_only=grow_only)

    # =============================================================================
    # Window policy
    # =============================================================================

    def _auto_dismiss_allowed(self) -> bool:
        """Single decision point for closing when the user leaves this window."""
        return (
            not self.window_controller.pinned
            and self._mode == PopupMode.READING
            and not self._closing
            and self.isVisible()
            and not self.isMinimized()
        )

    def _set_pinned(self, pinned: bool) -> None:
        if pinned == self.window_controller.pinned:
            self._apply_pin_state()
            return
        self.window_controller.set_pinned(pinned)
        self._apply_pin_state()
        self.pinned_changed.emit(pinned)

    def _apply_pin_state(self) -> None:
        """Sync every visible and native trace of the pin from one value."""
        pinned = self.window_controller.pinned
        if self.pin_btn.isChecked() != pinned:
            self.pin_btn.blockSignals(True)
            self.pin_btn.setChecked(pinned)
            self.pin_btn.blockSignals(False)
        tip = (
            "已固定：点击外部仍保持显示。点击取消固定"
            if pinned
            else "固定窗口：点击外部时仍保持显示"
        )
        self.pin_btn.setToolTip(tip)
        self.pin_btn.setAccessibleName("取消固定窗口" if pinned else "固定窗口")
        self.pin_btn.setAccessibleDescription(tip)
        self._refresh_icons()

    def _start_outside_click_monitor(self) -> None:
        self._stop_outside_click_monitor()
        self._install_outside_click_monitor()

    def _install_outside_click_monitor(self) -> None:
        if not self._closing and self.isVisible():
            self._native_monitor.start(self._handle_native_mouse, self._handle_app_switch)

    def _stop_outside_click_monitor(self) -> None:
        self._native_monitor.close()

    def _own_menu_open(self) -> bool:
        if QApplication.activePopupWidget() is not None:
            return True
        view = self.target_combo.view().window()
        return bool(view and view.isVisible())

    def _handle_native_mouse(self) -> None:
        """A click reached another application (never one of LingoFlow's windows)."""
        if not self._auto_dismiss_allowed():
            return
        if self._own_menu_open():
            # That click only closes our open menu or list.
            return
        self.outside_clicked.emit()

    def _handle_app_switch(self) -> None:
        """Another regular application became active, e.g. with Command-Tab."""
        if self._auto_dismiss_allowed():
            logger.debug("Another application became active; closing unpinned popup")
            self.dismiss()

    def _dismiss_from_outside(self) -> None:
        if self._auto_dismiss_allowed():
            self.dismiss()

    # =============================================================================
    # Helpers
    # =============================================================================

    def _format_source_language(self, language: Optional[str] = None) -> str:
        return language_name(language or self.settings.translation.source_language)

    def _set_target_language(self, language: str) -> None:
        """Set target language without firing language_changed."""
        index = self.target_combo.findData(language)
        if index < 0 or index == self.target_combo.currentIndex():
            return
        self._suppress_language_signal = True
        try:
            self.target_combo.setCurrentIndex(index)
        finally:
            self._suppress_language_signal = False

    def _source_edited(self) -> None:
        if self._mode != PopupMode.EDITING:
            return
        self.speech.stop(self._speech_owner)
        self.translate_btn.setEnabled(bool(self.get_source_text().strip()))

    def _restore_source(self) -> None:
        self.source_text.setPlainText(self._source_text)

    def _flash_status(self, text: str, delay_ms: int = 1500) -> None:
        if self._state in {"done", "idle"}:
            self._set_status(text)
            self._status_clear_timer.start(delay_ms)

    def _copy_source(self) -> None:
        QApplication.clipboard().setText(self.get_source_text())
        self._flash_status("已复制原文")

    def _copy_bilingual(self) -> None:
        QApplication.clipboard().setText(self.get_source_text() + "\n\n" + self._translated_text)
        self._flash_status("已复制原文和译文")

    def _copy_translation(self) -> None:
        """Copy exactly the translation that is displayed."""
        text = self.translation_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._copy_feedback_timer.start(1200)
            self._refresh_icons()
            self._flash_status("已复制译文")
            logger.debug("Translation copied to clipboard")

    def _scroll_to_latest(self) -> None:
        cursor = self.translation_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.translation_text.setTextCursor(cursor)
        scrollbar = self.translation_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_latest_button(self, *_args) -> None:
        scrollbar = self.translation_text.verticalScrollBar()
        away = scrollbar.value() < scrollbar.maximum() - 2
        paused = self._is_translating and self.translation_text.textCursor().hasSelection()
        self.latest_btn.setVisible(
            self._mode == PopupMode.READING and bool(self._translated_text) and (away or paused)
        )

    # =============================================================================
    # Speech
    # =============================================================================

    def _speak_source(self) -> None:
        self._speak("source")

    def _speak_translation(self) -> None:
        self._speak("translation")

    def _speak(self, kind: str) -> None:
        if self.speech.is_active(self._speech_owner, kind):
            self.speech.stop(self._speech_owner)
            return
        source = kind == "source"
        widget = self.source_text if source else self.translation_text
        text = widget.textCursor().selectedText().replace(" ", "\n")
        text = text or (self.get_source_text() if source else self._translated_text)
        if source:
            language = self._detected_source or self.settings.translation.source_language
        else:
            language = self.get_target_language()
        if language in {"auto", "English"}:
            locale = self.settings.speech.source_locale
        else:
            locale = LANGUAGE_LOCALES.get(language, "")
        if language == "English" and not locale.startswith("en-"):
            locale = "en-US"
        self.speech.speak(
            SpeechRequest(
                owner=self._speech_owner,
                kind=kind,
                text=text,
                locale=locale,
                voice=(
                    self.settings.speech.source_voice
                    if source
                    else self.settings.speech.target_voice
                ),
                rate=self.settings.speech.rate,
            )
        )

    def _speech_failed(self, owner: str, message: str) -> None:
        if owner == self._speech_owner:
            self._set_status(f"无法朗读：{message}", error=True)

    def _source_context_menu(self, position) -> None:
        menu = self.source_text.createStandardContextMenu()
        menu.addSeparator()
        if self._mode == PopupMode.EDITING:
            restore = menu.addAction("恢复原来的原文")
            restore.setEnabled(self.get_source_text() != self._source_text)
            restore.triggered.connect(self._restore_source)
        action = menu.addAction("朗读选中文字")
        action.setEnabled(self.source_text.textCursor().hasSelection())
        action.triggered.connect(self._speak_source)
        menu.exec(self.source_text.mapToGlobal(position))
        menu.deleteLater()

    def _translation_context_menu(self, position) -> None:
        menu = self.translation_text.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("朗读选中文字")
        action.setEnabled(
            self.translation_text.textCursor().hasSelection() and not self._is_translating
        )
        action.triggered.connect(self._speak_translation)
        menu.exec(self.translation_text.mapToGlobal(position))
        menu.deleteLater()

    # =============================================================================
    # Event Handlers
    # =============================================================================

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._mode == PopupMode.EDITING:
                self._cancel_edit()
            else:
                self.dismiss()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        # Minimizing is not a cancellation request; a closed window stops speaking.
        if hasattr(self, "window_controller") and not self.isMinimized():
            self._stop_outside_click_monitor()
            self.speech.stop(self._speech_owner)
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if hasattr(self, "window_controller"):
            self.window_controller.reassert_level()
            self._start_outside_click_monitor()
            self._update_source_preview()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "window_controller"):
            if not self.isMinimized() and self.isVisible():
                self.window_controller.reassert_level()
                self._start_outside_click_monitor()

    def closeEvent(self, event) -> None:  # noqa: N802
        if event.spontaneous() and not self._closing and not self._confirm_discard():
            # The native close button must not silently drop unsubmitted edits.
            event.ignore()
            return
        self._closing = True
        self.speech.stop(self._speech_owner)
        self.window_controller.save()
        self._status_clear_timer.stop()
        self._fit_timer.stop()
        self._copy_feedback_timer.stop()
        self._stop_outside_click_monitor()
        should_emit_closed = not self._dismiss_emitted and (
            self.isVisible() or self._is_translating or bool(self._source_text)
        )
        self._is_translating = False
        self._source_text = ""
        self._translated_text = ""
        self.translation_text.clear()
        self.source_text.clear()
        self.status_label.setText("")
        self.clearFocus()
        if should_emit_closed:
            self._dismiss_emitted = True
            self.closed.emit()
        event.accept()
