"""
Translation popup window for LingoFlow.

Displays source text and streaming translation results.
"""

import platform
from typing import Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lingoflow.config.constants import (
    POPUP_MAX_HEIGHT,
    POPUP_MAX_WIDTH,
    POPUP_MIN_HEIGHT,
    POPUP_MIN_WIDTH,
    SUPPORTED_LANGUAGES,
)
from lingoflow.config.settings import AppSettings
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

    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()

        self.settings = settings or AppSettings.load()
        self.signals = TranslationSignals()

        self._source_text = ""
        self._translated_text = ""
        self._is_translating = False
        self._suppress_language_signal = False
        self._dismiss_emitted = False
        self._closing = False
        self._macos_event_monitors = []
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(self._clear_status)
        self._outside_click_monitor_timer = QTimer(self)
        self._outside_click_monitor_timer.setSingleShot(True)
        self._outside_click_monitor_timer.timeout.connect(self._install_outside_click_monitor)

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        logger.debug("TranslationPopup initialized")

    # =============================================================================
    # Setup Methods
    # =============================================================================

    def _setup_window(self) -> None:
        """Configure window properties."""
        # Frameless, always on top, tool window (no taskbar entry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        # Allow transparency for rounded corners
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Size constraints
        self.setMinimumWidth(POPUP_MIN_WIDTH)
        self.setMaximumWidth(POPUP_MAX_WIDTH)
        self.setMinimumHeight(POPUP_MIN_HEIGHT)
        self.setMaximumHeight(POPUP_MAX_HEIGHT)

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

        # Close button
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeButton")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.clicked.connect(self.dismiss)
        header_layout.addWidget(self.close_btn)

        container_layout.addLayout(header_layout)

        # --- Source text (collapsible) ---
        self.source_text_label = QLabel()
        self.source_text_label.setObjectName("sourceText")
        self.source_text_label.setWordWrap(True)
        self.source_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_text_label.setVisible(self.settings.ui.show_source_text)
        container_layout.addWidget(self.source_text_label)

        # Separator
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setObjectName("separator")
        self.separator.setVisible(self.settings.ui.show_source_text)
        container_layout.addWidget(self.separator)

        # --- Translation output ---
        self.translation_text = QTextEdit()
        self.translation_text.setObjectName("translationText")
        self.translation_text.setReadOnly(True)
        self.translation_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.translation_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.translation_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        container_layout.addWidget(self.translation_text)

        # --- Footer: Copy button and status ---
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        footer_layout.addWidget(self.status_label)

        footer_layout.addStretch()

        # Copy button
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("copyButton")
        self.copy_btn.clicked.connect(self._copy_translation)
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
        self.outside_clicked.connect(self.dismiss)

    def _get_stylesheet(self) -> str:
        """Return the popup stylesheet."""
        font_size = self.settings.ui.font_size
        opacity = self.settings.ui.popup_opacity

        # Convert opacity to alpha (0-255)
        alpha = int(opacity * 255)
        bg_color = f"rgba(30, 30, 30, {alpha})"

        return f"""
            #popupContainer {{
                background-color: {bg_color};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }}

            #sourceLabel, #arrowLabel {{
                color: rgba(255, 255, 255, 0.6);
                font-size: {font_size - 2}px;
            }}

            #targetCombo {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {font_size - 2}px;
            }}

            #targetCombo::drop-down {{
                border: none;
            }}

            #targetCombo QAbstractItemView {{
                background-color: rgb(45, 45, 45);
                color: white;
                selection-background-color: rgb(70, 70, 70);
            }}

            #closeButton {{
                background-color: transparent;
                color: rgba(255, 255, 255, 0.6);
                border: none;
                font-size: 16px;
                font-weight: bold;
            }}

            #closeButton:hover {{
                color: white;
                background-color: rgba(255, 0, 0, 0.3);
                border-radius: 4px;
            }}

            #sourceText {{
                color: rgba(255, 255, 255, 0.7);
                font-size: {font_size - 1}px;
                padding: 4px 0;
            }}

            #separator {{
                background-color: rgba(255, 255, 255, 0.1);
                max-height: 1px;
            }}

            #translationText {{
                background-color: transparent;
                color: white;
                border: none;
                font-size: {font_size}px;
            }}

            #statusLabel {{
                color: rgba(255, 255, 255, 0.5);
                font-size: {font_size - 3}px;
            }}

            #copyButton {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: {font_size - 2}px;
            }}

            #copyButton:hover {{
                background-color: rgba(255, 255, 255, 0.2);
            }}

            #copyButton:pressed {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
        """

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
        self._source_text = source_text
        self._translated_text = ""
        self._dismiss_emitted = False
        self._closing = False
        self._status_clear_timer.stop()

        # Update source text display
        self.source_text_label.setText(source_text)
        self.source_label.setText(self._format_source_language(source_language))

        # Clear previous translation
        self.translation_text.clear()

        # Set target language if specified (suppress signal to avoid re-entrancy)
        if target_language:
            self._set_target_language(target_language)

        # Position and show
        self._position_near_cursor()
        self.show()
        self.raise_()
        self._start_outside_click_monitor()

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
        return self._source_text

    def update_settings(self, settings: AppSettings) -> None:
        """Update popup with new settings."""
        self.settings = settings
        self.container.setStyleSheet(self._get_stylesheet())
        self.source_text_label.setVisible(settings.ui.show_source_text)
        self.separator.setVisible(settings.ui.show_source_text)
        self._set_target_language(settings.translation.target_language)
        self.source_label.setText(self._format_source_language())

    # =============================================================================
    # Private Slots
    # =============================================================================

    def _on_chunk_received(self, chunk: str) -> None:
        """Handle incoming translation chunk."""
        self._restore_if_translating()
        self._translated_text += chunk
        self.translation_text.insertPlainText(chunk)

        # Auto-scroll to bottom
        scrollbar = self.translation_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_translation_started(self) -> None:
        """Handle translation start."""
        self._is_translating = True
        self.status_label.setText("Translating...")
        self.copy_btn.setEnabled(False)

    def _on_translation_finished(self) -> None:
        """Handle translation completion."""
        self._is_translating = False

        # Show character count
        char_count = len(self._translated_text)
        self.status_label.setText(f"Done · {char_count} chars")
        self.copy_btn.setEnabled(True)

        # Clear status after a delay
        self._schedule_status_clear(3000)

    def _on_translation_error(self, message: str) -> None:
        """Handle translation error."""
        self._is_translating = False
        self.status_label.setText(f"Error: {message}")
        self.copy_btn.setEnabled(True)

        # Show error in translation area
        self.translation_text.setPlainText(f"⚠️ {message}")

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
        if platform.system() != "Darwin":
            return

        self._outside_click_monitor_timer.start(350)

    def _install_outside_click_monitor(self) -> None:
        """Install native outside-click monitors after show-time events settle."""
        if self._closing or not self.isVisible():
            return

        try:
            from AppKit import (
                NSEvent,
                NSEventMaskLeftMouseDown,
                NSEventMaskOtherMouseDown,
                NSEventMaskRightMouseDown,
            )
        except Exception as e:
            logger.debug(f"macOS outside-click monitor unavailable: {e}")
            return

        mask = NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown | NSEventMaskOtherMouseDown

        def is_outside_popup() -> bool:
            try:
                cursor_pos = QCursor.pos()
                if self.frameGeometry().contains(cursor_pos):
                    return False

                combo_popup = self.target_combo.view().window()
                if (
                    combo_popup
                    and combo_popup.isVisible()
                    and combo_popup.frameGeometry().contains(cursor_pos)
                ):
                    return False

                return True
            except RuntimeError:
                return False

        def global_handler(event) -> None:
            if is_outside_popup() and not self._is_translating:
                self.outside_clicked.emit()

        def local_handler(event):
            if is_outside_popup() and not self._is_translating:
                self.outside_clicked.emit()
            return event

        try:
            global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                mask,
                global_handler,
            )
            local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                mask,
                local_handler,
            )
            self._macos_event_monitors = [
                monitor for monitor in (global_monitor, local_monitor) if monitor
            ]
        except Exception as e:
            logger.debug(f"Could not install macOS outside-click monitor: {e}")
            self._macos_event_monitors = []

    def _stop_outside_click_monitor(self) -> None:
        """Remove native outside-click monitors."""
        self._outside_click_monitor_timer.stop()
        if not self._macos_event_monitors:
            return

        try:
            from AppKit import NSEvent

            for monitor in self._macos_event_monitors:
                NSEvent.removeMonitor_(monitor)
        except Exception as e:
            logger.debug(f"Could not remove macOS outside-click monitor: {e}")
        finally:
            self._macos_event_monitors = []

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

    def _copy_translation(self) -> None:
        """Copy translation to clipboard."""
        if self._translated_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._translated_text)
            self.status_label.setText("Copied!")
            self._schedule_status_clear(1500)
            logger.debug("Translation copied to clipboard")

    def _position_near_cursor(self) -> None:
        """Position the popup near the cursor."""
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)

        if screen is None:
            screen = QApplication.primaryScreen()

        screen_rect = screen.availableGeometry()

        # Calculate popup position (below and to the right of cursor)
        x = cursor_pos.x() + 10
        y = cursor_pos.y() + 20

        # Adjust if popup would go off screen
        popup_width = self.width() or POPUP_MIN_WIDTH
        popup_height = self.height() or POPUP_MIN_HEIGHT

        if x + popup_width > screen_rect.right():
            x = cursor_pos.x() - popup_width - 10

        if y + popup_height > screen_rect.bottom():
            y = cursor_pos.y() - popup_height - 20

        # Ensure within screen bounds
        x = max(screen_rect.left(), min(x, screen_rect.right() - popup_width))
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - popup_height))

        self.move(x, y)

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

    def focusOutEvent(self, event) -> None:  # noqa: N802
        """Handle focus loss — close popup if configured."""
        if self.settings.ui.hide_on_focus_loss and not self._is_translating:
            self.dismiss()
            event.accept()
        else:
            super().focusOutEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        """Treat macOS tool-window auto-hide as a dismissed popup."""
        super().hideEvent(event)
        if (
            self.settings.ui.hide_on_focus_loss
            and not self._dismiss_emitted
            and not self._closing
            and bool(self._source_text)
        ):
            if self._is_translating:
                QTimer.singleShot(0, self._restore_if_translating)
            else:
                QTimer.singleShot(0, self.dismiss)

    def _restore_if_translating(self) -> None:
        """Keep an active translation visible through transient macOS focus churn."""
        if self._is_translating and not self._closing and not self.isVisible():
            self.show()
            self.raise_()
            self._start_outside_click_monitor()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close."""
        self._closing = True
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
        self.source_text_label.clear()
        self.status_label.setText("")
        self.clearFocus()
        if should_emit_closed:
            self._dismiss_emitted = True
            self.closed.emit()
        event.accept()
