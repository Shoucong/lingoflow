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
    POPUP_MAX_WIDTH,
    SUPPORTED_LANGUAGES,
)
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

