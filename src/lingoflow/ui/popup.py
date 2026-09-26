"""
Translation popup window for LingoFlow.

Displays source text and streaming translation results.
"""

from pathlib import Path
from typing import Optional
from uuid import uuid4

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
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
from lingoflow.infrastructure.macos.event_monitor import OutsideClickMonitor
from lingoflow.infrastructure.macos.speech import MacOSSpeechService
from lingoflow.ui.theme import apply_palette, colors
from lingoflow.ui.translation_view import TranslationView
from lingoflow.ui.window_controller import PopupWindowController
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


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


# =============================================================================
# Translation Popup Window
# =============================================================================


class TranslationPopup(QWidget):
    """
    Popup window for displaying translations.

    Features:
    - Shows source text (optional)
    - Streams translation in real-time
    - Language selector
    - Copy button
    - Auto-positions near cursor

    Example:
        popup = TranslationPopup()
        popup.show_with_text("Hello world", target_language="Chinese (Simplified)")

        # Stream translation chunks
        popup.append_translation("你好")
        popup.append_translation("世界")
        popup.finish_translation()
    """

    # Emitted when user changes the target language while popup is visible
    language_changed = pyqtSignal(str)
    closed = pyqtSignal()
    outside_clicked = pyqtSignal()
    stop_requested = pyqtSignal()
    retry_requested = pyqtSignal(str)

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
        self._is_translating = False
        self._review_mode = False
        self._suppress_language_signal = False
        self._dismiss_emitted = False
        self._closing = False
        self._native_monitor = OutsideClickMonitor()
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(self._clear_status)
        self._outside_click_monitor_timer = QTimer(self)
        self._outside_click_monitor_timer.setSingleShot(True)
        self._outside_click_monitor_timer.timeout.connect(self._install_outside_click_monitor)
        self._inactive_timer = QTimer(self)
        self._inactive_timer.setSingleShot(True)
        self._inactive_timer.timeout.connect(self._dismiss_if_inactive)

        self._setup_window()
        self._setup_ui()
        self.window_controller = PopupWindowController(self, window_state_path)
        self.pin_btn.setChecked(self.window_controller.pinned)
        self._connect_signals()
        self._refresh_theme()

        logger.debug("TranslationPopup initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure window properties."""
        # Native decorations provide reliable dragging and edge/corner resizing.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowTitle("LingoFlow")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Size constraints
        self.setMinimumWidth(POPUP_MIN_WIDTH)
        self.setMinimumHeight(POPUP_MIN_HEIGHT)
        self.resize(640, 480)

    def _setup_ui(self) -> None:
        """Build the UI components."""
        # Main container with background and rounded corners
        self.container = QFrame(self)
        self.container.setObjectName("popupContainer")
        self.container.setStyleSheet(self._get_stylesheet())

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        # Container layout
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(8)

        # --- Header: Language selector and close button ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.source_label = QLabel(self._format_source_language())
        self.source_label.setObjectName("sourceLabel")
        header_layout.addWidget(self.source_label)

        # Arrow
        arrow_label = QLabel("→")
        arrow_label.setObjectName("arrowLabel")
        header_layout.addWidget(arrow_label)

        # Target language selector
        self.target_combo = QComboBox()
        self.target_combo.setObjectName("targetCombo")
        for lang in SUPPORTED_LANGUAGES:
            if lang != "auto":
                self.target_combo.addItem(lang)
        # Set default from settings
        default_target = self.settings.translation.target_language
        index = self.target_combo.findText(default_target)
        if index >= 0:
            self.target_combo.setCurrentIndex(index)
        header_layout.addWidget(self.target_combo)

        header_layout.addStretch()

        self.source_toggle = QPushButton("Source")
        self.source_toggle.setCheckable(True)
        self.source_toggle.setChecked(self.settings.ui.show_source_text)
        self.source_toggle.setToolTip("Show or hide the original text")
        header_layout.addWidget(self.source_toggle)

        self.pin_btn = QPushButton("Pin")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("Keep this window open and on top")
        header_layout.addWidget(self.pin_btn)

        # Close button
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeButton")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.clicked.connect(self.dismiss)
        header_layout.addWidget(self.close_btn)

        container_layout.addLayout(header_layout)

        self.text_splitter = TranslationView()
        self.source_text = self.text_splitter.source
        self.translation_text = self.text_splitter.target
        self.source_text.setVisible(self.settings.ui.show_source_text)
        container_layout.addWidget(self.text_splitter, 1)

        speech_layout = QHBoxLayout()
        self.speak_source_btn = QPushButton("Speak source")
        self.speak_source_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speak_source_btn.setToolTip("Read the selected source text, or the whole source")
        self.speak_source_btn.clicked.connect(self._speak_source)
        speech_layout.addWidget(self.speak_source_btn)
        self.speak_translation_btn = QPushButton("Speak translation")
        self.speak_translation_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speak_translation_btn.clicked.connect(self._speak_translation)
        speech_layout.addWidget(self.speak_translation_btn)
        self.speech_status = QLabel("")
        self.speech_status.setWordWrap(True)
        speech_layout.addWidget(self.speech_status, 1)
        container_layout.addLayout(speech_layout)

        # --- Footer: Copy button and status ---
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        footer_layout.addWidget(self.status_label)

        footer_layout.addStretch()

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        footer_layout.addWidget(self.stop_btn)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.clicked.connect(self._on_retry_clicked)
        footer_layout.addWidget(self.retry_btn)

        self.latest_btn = QPushButton("Latest")
        self.latest_btn.setToolTip("Clear the selection and follow new output")
        self.latest_btn.clicked.connect(self._scroll_to_latest)
        footer_layout.addWidget(self.latest_btn)

        # Copy button
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("copyButton")
        self.copy_menu = QMenu(self.copy_btn)
        self.copy_target_action = self.copy_menu.addAction("Copy translation")
        self.copy_target_action.triggered.connect(self._copy_translation)
        self.copy_source_action = self.copy_menu.addAction("Copy source")
        self.copy_source_action.triggered.connect(self._copy_source)
        self.copy_both_action = self.copy_menu.addAction("Copy bilingual")
        self.copy_both_action.triggered.connect(self._copy_bilingual)
        self.copy_menu.aboutToShow.connect(self._update_copy_actions)
        self.copy_btn.setMenu(self.copy_menu)
        footer_layout.addWidget(self.copy_btn)

        container_layout.addLayout(footer_layout)

    def _connect_signals(self) -> None:
        """Connect thread-safe signals to UI updates."""
        self.signals.chunk_received.connect(self._on_chunk_received)
        self.signals.translation_started.connect(self._on_translation_started)
        self.signals.translation_finished.connect(self._on_translation_finished)
        self.signals.translation_error.connect(self._on_translation_error)
        self.signals.translation_cleared.connect(self._on_translation_cleared)

        # Language change triggers re-translation
        self.target_combo.currentTextChanged.connect(self._on_language_changed)
        self.outside_clicked.connect(self._dismiss_from_outside)
        self.pin_btn.toggled.connect(self._set_pinned)
        self.source_toggle.toggled.connect(self.source_text.setVisible)
        self.translation_text.verticalScrollBar().valueChanged.connect(self._update_latest_button)
        self.translation_text.verticalScrollBar().rangeChanged.connect(self._update_latest_button)
        self.translation_text.selectionChanged.connect(self._update_latest_button)
        self._update_latest_button()
        self.speech.state_changed.connect(self._update_speech_buttons)
        self.speech.failed.connect(self._speech_failed)
        self.source_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.source_text.customContextMenuRequested.connect(self._source_context_menu)
        self.translation_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.translation_text.customContextMenuRequested.connect(self._translation_context_menu)
        self._update_speech_buttons()
        self.source_text.textChanged.connect(self._source_edited)
        self._retry_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._retry_shortcut.activated.connect(self._on_retry_clicked)
        QApplication.styleHints().colorSchemeChanged.connect(self._refresh_theme)

    def _get_stylesheet(self) -> str:
        theme = colors(self.settings.ui.theme)
        font = self.settings.ui.font_size
        return f"""
            #popupContainer {{ background: {theme['background']}; color: {theme['text']}; }}
            QLabel {{ color: {theme['muted']}; font-size: {font - 2}px; }}
            QTextEdit {{ background: {theme['control']}; color: {theme['text']};
                border: 1px solid {theme['border']}; border-radius: 4px; padding: 6px;
                font-size: {font}px; selection-background-color: #2874d0; selection-color: white; }}
            QPushButton, QComboBox {{ background: {theme['control']}; color: {theme['text']};
                border: 1px solid {theme['border']}; border-radius: 4px; padding: 4px 8px;
                font-size: {font - 2}px; }}
            QPushButton:checked {{ background: #2874d0; color: white; }}
            QPushButton:disabled {{ color: {theme['muted']}; }}
            QComboBox QAbstractItemView, QMenu {{ background: {theme['control']};
                color: {theme['text']}; selection-background-color: #2874d0; }}
            QSplitter::handle {{ background: {theme['border']}; height: 5px; width: 5px; }}
        """

    def _refresh_theme(self, *_args) -> None:
        apply_palette(self, self.settings.ui.theme)
        self.container.setStyleSheet(self._get_stylesheet())
        self.setWindowOpacity(self.settings.ui.popup_opacity)
        self.text_splitter.setOrientation(
            Qt.Orientation.Horizontal
            if self.settings.ui.bilingual_layout == "side_by_side"
            else Qt.Orientation.Vertical
        )

    # =============================================================================
    # Public Methods
    # =============================================================================

    def show_with_text(
        self,
        source_text: str,
        target_language: Optional[str] = None,
        source_language: Optional[str] = None,
    ) -> None:
        """
        Show the popup with source text and prepare for translation.

        Args:
            source_text: Text to translate
            target_language: Target language (uses current selection if None)
            source_language: Source language display (uses settings if None)
        """
        self.speech.stop(self._speech_owner)
        self.speech_status.clear()
        self._source_text = source_text
        self._review_mode = False
        self._translated_text = ""
        self._dismiss_emitted = False
        self._closing = False
        self._status_clear_timer.stop()

        # Update source text display
        self.source_text.setPlainText(source_text)
        self.source_toggle.setChecked(self.settings.ui.show_source_text and len(source_text) <= 400)
        self.source_label.setText(self._format_source_language(source_language))

        # Clear previous translation
        self.translation_text.clear()

        # Set target language if specified (suppress signal to avoid re-entrancy)
        if target_language:
            self._set_target_language(target_language)

        # Position and show
        self.window_controller.prepare_show()
        self.show()
        self.raise_()
        self._start_outside_click_monitor()
        self._update_speech_buttons()

        if self.settings.privacy.allow_content_logging:
            logger.debug(f"Popup shown with text: {source_text[:80]}...")
        else:
            logger.debug(f"Popup shown with source text ({len(source_text)} chars)")

    def append_translation(self, chunk: str) -> None:
        """
        Append a translation chunk (thread-safe).

        Call this from any thread; uses signals for safety.
        """
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
        """Get the currently selected target language."""
        return self.target_combo.currentText()

    def get_source_text(self) -> str:
        """Get the current source text."""
        return self.source_text.toPlainText()

    @property
    def is_reviewing(self) -> bool:
        return self._review_mode

    def prepare_review(self) -> None:
        self._is_translating = False
        self._review_mode = True
        self._status_clear_timer.stop()
        self.source_toggle.setChecked(True)
        self.source_text.setReadOnly(False)
        self.retry_btn.setText("Translate")
        self.retry_btn.setEnabled(bool(self.get_source_text().strip()))
        self.stop_btn.setEnabled(False)
        self.translation_text.setPlaceholderText("Your translation will appear here.")
        self.status_label.setText("Review source, then Translate · ⌘↵")
        self.status_label.setToolTip("")
        self.activateWindow()
        self.source_text.setFocus()

    def update_settings(self, settings: AppSettings) -> None:
        """Update popup with new settings."""
        self.settings = settings
        self._refresh_theme()
        self.source_toggle.setChecked(settings.ui.show_source_text)
        self._set_target_language(settings.translation.target_language)
        self.source_label.setText(self._format_source_language())

    # =============================================================================
    # Private Slots
    # =============================================================================

    def _on_chunk_received(self, chunk: str) -> None:
        """Append output without replacing a selection or moving the reader."""
        if not chunk:
            return

        self.text_splitter.append_output(chunk)
        self._translated_text += chunk
        self.copy_btn.setEnabled(bool(self.get_source_text()))
        self._update_speech_buttons()

    def _on_translation_started(self) -> None:
        """Handle translation start."""
        self._is_translating = True
        self._review_mode = False
        self.source_text.setReadOnly(True)
        self.retry_btn.setText("Retry")
        self._status_clear_timer.stop()
        self.status_label.setText("Translating...")
        self.status_label.setToolTip("")
        self.translation_text.setPlaceholderText("Waiting for the model…")
        self.stop_btn.setEnabled(True)
        self.copy_btn.setEnabled(bool(self.get_source_text()))
        self.speech.stop(self._speech_owner)
        self._update_speech_buttons()

    def _on_translation_finished(self) -> None:
        """Handle translation completion."""
        self._is_translating = False
        self.source_text.setReadOnly(False)
        self.stop_btn.setEnabled(False)
        self._update_speech_buttons()

        # Show character count
        char_count = len(self._translated_text)
        self.status_label.setText(f"Done · {char_count} chars")
        self.copy_btn.setEnabled(True)

        # Clear status after a delay
        self._schedule_status_clear(3000)

    def _on_translation_error(self, message: str) -> None:
        """Handle translation error."""
        self._is_translating = False
        self.source_text.setReadOnly(False)
        self._status_clear_timer.stop()
        self.stop_btn.setEnabled(False)
        self._update_speech_buttons()
        self.status_label.setText("Failed · partial result" if self._translated_text else "Failed")
        self.status_label.setToolTip(message)
        self.copy_btn.setEnabled(bool(self.get_source_text()))
        self.translation_text.setPlaceholderText(message)

    def set_progress(self, completed: int, total: int) -> None:
        if self._is_translating and total > 1:
            self.status_label.setText(f"Translating · {completed}/{total} parts")

    def stop_translation(self) -> None:
        """Keep useful partial text without labeling it a completed translation."""
        self._is_translating = False
        self.source_text.setReadOnly(False)
        self._status_clear_timer.stop()
        self.stop_btn.setEnabled(False)
        self._update_speech_buttons()
        self.status_label.setText("Stopped · partial result")
        self.copy_btn.setEnabled(bool(self.get_source_text()))

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()

    def _on_retry_clicked(self) -> None:
        self.retry_requested.emit(self.get_source_text())

    def _on_translation_cleared(self) -> None:
        """Handle clearing translation output (for retries)."""
        self._translated_text = ""
        self.translation_text.clear()
        self.status_label.setText("Retrying...")

    def _on_language_changed(self, language: str) -> None:
        """Handle target language change."""
        logger.debug(f"Target language changed to: {language}")
        # Only emit if popup is visible, has source text, and not a programmatic change
        if self.isVisible() and self._source_text and not self._suppress_language_signal:
            self.language_changed.emit(language)

    def dismiss(self) -> None:
        """Dismiss the popup as a closed interaction."""
        self._closing = True
        self.close()

    def _clear_status(self) -> None:
        """Clear transient status text while the popup is alive."""
        self.status_label.setText("")

    def _schedule_status_clear(self, delay_ms: int) -> None:
        """Clear transient status text using a timer owned by this popup."""
        self._status_clear_timer.start(delay_ms)

    def _start_outside_click_monitor(self) -> None:
        """Close the popup on outside clicks that Qt does not deliver on macOS."""
        self._stop_outside_click_monitor()
        if not self.settings.ui.hide_on_focus_loss:
            return

        self._outside_click_monitor_timer.start(350)

    def _install_outside_click_monitor(self) -> None:
        if not self._closing and self.isVisible():
            self._native_monitor.start(self._handle_native_mouse)

    def _handle_native_mouse(self) -> None:
        if not self._auto_dismiss_allowed():
            return
        cursor = QCursor.pos()
        if self.frameGeometry().contains(cursor) or QApplication.activePopupWidget() is not None:
            return
        combo = self.target_combo.view().window()
        if combo and combo.isVisible() and combo.frameGeometry().contains(cursor):
            return
        self.outside_clicked.emit()

    def _stop_outside_click_monitor(self) -> None:
        self._outside_click_monitor_timer.stop()
        self._native_monitor.close()

    def _format_source_language(self, language: Optional[str] = None) -> str:
        """Format source language for the popup header."""
        source_language = language or self.settings.translation.source_language
        if source_language.lower() == "auto":
            return "Auto"
        return source_language

    def _set_target_language(self, language: str) -> None:
        """Set target language without firing language_changed."""
        index = self.target_combo.findText(language)
        if index < 0 or index == self.target_combo.currentIndex():
            return

        self._suppress_language_signal = True
        try:
            self.target_combo.setCurrentIndex(index)
        finally:
            self._suppress_language_signal = False

    def _source_edited(self) -> None:
        self.speech.stop(self._speech_owner)
        if not self._is_translating and self.get_source_text() != self._source_text:
            self._review_mode = True
            self._status_clear_timer.stop()
            self.status_label.setText("Source edited · translate again · ⌘↵")
            self.status_label.setToolTip("")
            self.retry_btn.setText("Translate edits")
        self.retry_btn.setEnabled(bool(self.get_source_text().strip()))
        self.copy_btn.setEnabled(bool(self.get_source_text()))
        self._update_speech_buttons()

    def _restore_source(self) -> None:
        self.source_text.setPlainText(self._source_text)

    def _update_copy_actions(self) -> None:
        self.copy_source_action.setEnabled(bool(self.get_source_text()))
        self.copy_target_action.setEnabled(bool(self._translated_text))
        self.copy_both_action.setEnabled(bool(self._translated_text))

    def _copy_source(self) -> None:
        QApplication.clipboard().setText(self.get_source_text())

    def _copy_bilingual(self) -> None:
        QApplication.clipboard().setText(self.get_source_text() + "\n\n" + self._translated_text)

    def _copy_translation(self) -> None:
        """Copy translation to clipboard."""
        if self._translated_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._translated_text)
            self.status_label.setText("Copied!")
            self._schedule_status_clear(1500)
            logger.debug("Translation copied to clipboard")

    def _set_pinned(self, pinned: bool) -> None:
        self.window_controller.set_pinned(pinned)
        self.pin_btn.setText("Pinned" if pinned else "Pin")
        self._start_outside_click_monitor()

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
        text = widget.textCursor().selectedText().replace("\u2029", "\n")
        text = text or (self.get_source_text() if source else self._translated_text)
        language = (
            self.settings.translation.source_language if source else self.get_target_language()
        )
        if language in {"auto", "English"}:
            locale = self.settings.speech.source_locale
        else:
            locale = LANGUAGE_LOCALES.get(language, "")
        if language == "English" and not locale.startswith("en-"):
            locale = "en-US"
        self.speech_status.clear()
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

    def _update_speech_buttons(self) -> None:
        self.speak_source_btn.setText(
            "Stop source" if self.speech.is_active(self._speech_owner, "source") else "Speak source"
        )
        self.speak_translation_btn.setText(
            "Stop translation"
            if self.speech.is_active(self._speech_owner, "translation")
            else "Speak translation"
        )
        self.speak_source_btn.setEnabled(bool(self.get_source_text().strip()))
        self.speak_translation_btn.setEnabled(
            bool(self._translated_text) and not self._is_translating
        )

    def _speech_failed(self, owner: str, message: str) -> None:
        if owner == self._speech_owner:
            self.speech_status.setText(message)

    def _source_context_menu(self, position) -> None:
        menu = self.source_text.createStandardContextMenu()
        menu.addSeparator()
        restore = menu.addAction("Restore original source")
        restore.setEnabled(not self._is_translating and self.get_source_text() != self._source_text)
        restore.triggered.connect(self._restore_source)
        action = menu.addAction("Speak selected text")
        action.setEnabled(self.source_text.textCursor().hasSelection())
        action.triggered.connect(self._speak_source)
        menu.exec(self.source_text.mapToGlobal(position))
        menu.deleteLater()

    def _translation_context_menu(self, position) -> None:
        menu = self.translation_text.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Speak selected text")
        action.setEnabled(
            self.translation_text.textCursor().hasSelection() and not self._is_translating
        )
        action.triggered.connect(self._speak_translation)
        menu.exec(self.translation_text.mapToGlobal(position))
        menu.deleteLater()

    def _auto_dismiss_allowed(self) -> bool:
        return (
            self.settings.ui.hide_on_focus_loss
            and not self.window_controller.pinned
            and not self.window_controller.reconfiguring
            and not self._is_translating
            and not self._review_mode
            and not self._closing
            and not self.isMinimized()
        )

    def _dismiss_from_outside(self) -> None:
        if self._auto_dismiss_allowed():
            self.dismiss()

    def _dismiss_if_inactive(self) -> None:
        if (
            self.isVisible()
            and not self.isActiveWindow()
            and QApplication.activePopupWidget() is None
            and not self.target_combo.view().window().isVisible()
        ):
            self._dismiss_from_outside()

    def _scroll_to_latest(self) -> None:
        cursor = self.translation_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.translation_text.setTextCursor(cursor)
        scrollbar = self.translation_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_latest_button(self, *_args) -> None:
        scrollbar = self.translation_text.verticalScrollBar()
        self.latest_btn.setEnabled(
            scrollbar.value() < scrollbar.maximum() - 2
            or self.translation_text.textCursor().hasSelection()
        )

    # =============================================================================
    # Event Handlers
    # =============================================================================

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle key press events."""
        # Escape closes the popup
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.ActivationChange
            and hasattr(self, "window_controller")
            and not self._closing
        ):
            self._inactive_timer.start(0)

    def hideEvent(self, event) -> None:  # noqa: N802
        # Minimizing and native flag changes are not cancellation requests.
        if hasattr(self, "_outside_click_monitor_timer"):
            self._stop_outside_click_monitor()
        if hasattr(self, "window_controller") and not self.window_controller.reconfiguring:
            self.speech.stop(self._speech_owner)
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if hasattr(self, "window_controller"):
            self._start_outside_click_monitor()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close."""
        self._closing = True
        self.speech.stop(self._speech_owner)
        self._inactive_timer.stop()
        self.window_controller.save()
        self._status_clear_timer.stop()
        self._outside_click_monitor_timer.stop()
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
