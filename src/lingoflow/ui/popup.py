"""
Translation popup window for LingoFlow.

Displays source text and streaming translation results
"""

import threading
from typing import Optional

from PyQt6.QtCore import Qt, Qpoint, Qtimer, pyqtSignal, QObject
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

# =========================================================
# Signals Bridge for Thread-Safe UI Updates
# =========================================================

class TranslationSignals(QObject):
    """Signals for thread-safe communication with the popup."""

    chunk_received = pyqtSignal(str) # New text chunk
    translation_started = pyqtSignal() # Translation began
    translation_finished = pyqtSignal() # Translation complete
    translation_error = pyqtSignal(str) # Error message


# =========================================================
# Translation Popup Window
# =========================================================

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

    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()

        self.settings = settings or AppSettings.load()
        self.signals = TranslationSignals()

        self._source_text = ""
        self._translated_text = ""
        self._is_translating = False

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        logger.debug("TranslationPopup initialized")
    
    # =========================================================
    # Setup Methods
    # ========================================================

    def _setup_window(self) -> None: 
        """Configure window properties."""
        # Freamless, always on top, tool window (no taskbar entry)
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