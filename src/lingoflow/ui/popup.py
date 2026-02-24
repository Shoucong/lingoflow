"""
Translation popup window for LingoFlow.

Displays source text and streaming translation results.
"""

import threading
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QFontMetrics, QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QComboBox,
    QFrame,
    QApplication,
    QSizePolicy,
)

from lingoflow.config.settings import AppSettings
from lingoflow.config.constants import (
    POPUP_MIN_WIDTH,
    POPUP_MAX_WIDTH,
    POPUP_MIN_HEIGHT,
    POPUP_MAX_HEIGHT,
    SUPPORTED_LANGUAGES,
)
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

    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()
        
        self.settings = settings or AppSettings.load()
        self.signals = TranslationSignals()
        
        self._source_text = ""
        self._translated_text = ""
        self._is_translating = False
        self._suppress_language_signal = False
        
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
        
        # Source language (auto-detect for now)
        self.source_label = QLabel("Auto")
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
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)
        
        container_layout.addLayout(header_layout)
        
        # --- Source text (collapsible) ---
        self.source_text_label = QLabel()
        self.source_text_label.setObjectName("sourceText")
        self.source_text_label.setWordWrap(True)
        self.source_text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
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
        self.translation_text.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.translation_text.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
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
        
        # Language change triggers re-translation
        self.target_combo.currentTextChanged.connect(self._on_language_changed)

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
    ) -> None:
        """
        Show the popup with source text and prepare for translation.
        
        Args:
            source_text: Text to translate
            target_language: Target language (uses current selection if None)
        """
        self._source_text = source_text
        self._translated_text = ""
        
        # Update source text display
        self.source_text_label.setText(source_text)
        
        # Clear previous translation
        self.translation_text.clear()
        
        # Set target language if specified (suppress signal to avoid re-entrancy)
        if target_language:
            index = self.target_combo.findText(target_language)
            if index >= 0:
                self._suppress_language_signal = True
                self.target_combo.setCurrentIndex(index)
                self._suppress_language_signal = False
        
        # Position and show
        self._position_near_cursor()
        self.show()
        self.raise_()
        self.activateWindow()
        
        logger.debug(f"Popup shown with text: {source_text[:50]}...")

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

    # =============================================================================
    # Private Slots
    # =============================================================================

    def _on_chunk_received(self, chunk: str) -> None:
        """Handle incoming translation chunk."""
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
        self.status_label.setText("Done")
        self.copy_btn.setEnabled(True)
        
        # Clear status after a delay
        QTimer.singleShot(2000, lambda: self.status_label.setText(""))

    def _on_translation_error(self, message: str) -> None:
        """Handle translation error."""
        self._is_translating = False
        self.status_label.setText(f"Error: {message}")
        self.copy_btn.setEnabled(True)
        
        # Show error in translation area
        self.translation_text.setPlainText(f"⚠️ {message}")

    def _on_language_changed(self, language: str) -> None:
        """Handle target language change."""
        logger.debug(f"Target language changed to: {language}")
        # Only emit if popup is visible, has source text, and not a programmatic change
        if self.isVisible() and self._source_text and not self._suppress_language_signal:
            self.language_changed.emit(language)

    def _copy_translation(self) -> None:
        """Copy translation to clipboard."""
        if self._translated_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._translated_text)
            self.status_label.setText("Copied!")
            QTimer.singleShot(1500, lambda: self.status_label.setText(""))
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

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        # Escape closes the popup
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        """Handle focus loss — hide popup if configured."""
        if self.settings.ui.hide_on_focus_loss:
            self.hide()
        else:
            super().focusOutEvent(event)