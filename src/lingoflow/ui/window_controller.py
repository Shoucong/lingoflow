"""Persistent geometry and native window policy for the translation panel."""

from __future__ import annotations

import json
import weakref
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QWidget

from lingoflow.config import constants
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


def fit_to_screen(rect: QRect, available: QRect) -> QRect:
    """Clamp both dimensions and position, including negative screen origins."""
    width = min(max(1, rect.width()), available.width())
    height = min(max(1, rect.height()), available.height())
    x = min(max(rect.x(), available.left()), available.right() - width + 1)
    y = min(max(rect.y(), available.top()), available.bottom() - height + 1)
    return QRect(x, y, width, height)


class PopupWindowController(QObject):
    """Keep geometry separate from editable app settings and translation state."""

    def __init__(self, window: QWidget, state_path: Path | None = None):
        super().__init__(window)
        self._window = weakref.ref(window)
        self.path = state_path or constants.CONFIG_DIR / "window-state.json"
        self.state = self._load()
        self.pinned = self.state.get("pinned", False) is True
        self.reconfiguring = False
        self._prepared = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save)
        window.installEventFilter(self)
        app = QApplication.instance()
        if app:
            app.screenRemoved.connect(self._screen_removed)

    @property
    def window(self) -> QWidget:
        return self._window()

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _number(self, key: str, default: int) -> int:
        value = self.state.get(key)
        return value if type(value) is int and abs(value) < 100000 else default

    def prepare_show(self) -> None:
        """Place a fresh panel; preserve a visible panel's user-adjusted frame."""
        if self._prepared and self.window.isVisible():
            return
        cursor = QCursor.pos()
        position = QPoint(self._number("x", cursor.x()), self._number("y", cursor.y()))
        screen = QApplication.screenAt(position if self.pinned else cursor)
        screen = screen or QApplication.screenAt(cursor) or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        # Leave space for the system title bar and its frame.
        available.adjust(0, 0, 0, -32)
        rect = QRect(
            position if self.pinned else cursor + QPoint(10, 20),
            self.window.size(),
        )
        rect.setWidth(max(360, self._number("width", 640)))
        rect.setHeight(max(240, self._number("height", 480)))
        self.reconfiguring = True
        try:
            self.window.setMinimumSize(min(360, available.width()), min(240, available.height()))
            self.window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.pinned)
            self.window.setGeometry(fit_to_screen(rect, available))
        finally:
            self.reconfiguring = False
        self._prepared = True

    def set_pinned(self, pinned: bool) -> None:
        self.pinned = pinned
        geometry = self.window.geometry()
        visible = self.window.isVisible()
        self.reconfiguring = True
        try:
            self.window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
            self.window.setGeometry(geometry)
            if visible:
                self.window.show()
        finally:
            self.reconfiguring = False
        self.save()

    def save(self) -> None:
        self._save_timer.stop()
        if not self._prepared or self.window.isMinimized():
            return
        rect = self.window.geometry()
        self.state = {
            "width": rect.width(), "height": rect.height(),
            "x": rect.x(), "y": rect.y(), "pinned": self.pinned,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:
            logger.warning("Could not save window geometry: %s", error)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            event.type() in {QEvent.Type.Move, QEvent.Type.Resize}
            and self._prepared and not self.reconfiguring
            and self.window.isVisible() and not self.window.isMinimized()
        ):
            self._save_timer.start(250)
        return super().eventFilter(watched, event)

    def _screen_removed(self, _screen) -> None:
        if self.window.isVisible():
            screen = QApplication.screenAt(self.window.pos()) or QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry().adjusted(0, 0, 0, -32)
                self.window.setGeometry(fit_to_screen(self.window.geometry(), available))
