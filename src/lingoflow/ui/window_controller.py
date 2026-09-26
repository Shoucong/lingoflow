"""Geometry preferences and native window level for the translation panel.

Pinning is per window: it is never read from or written to disk, so every new
panel starts unpinned. Only the user's preferred size is remembered. A fresh
panel fits its content (short words stay compact, long text grows and then
scrolls) until the user resizes it; after that the panel keeps the user's size.
"""

from __future__ import annotations

import json
import weakref
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QWidget

from lingoflow.config import constants
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WIDTH = 460
DEFAULT_MAX_HEIGHT = 520
# Leave space for the system title bar and its frame.
TITLE_BAR_ALLOWANCE = 32


def fit_to_screen(rect: QRect, available: QRect) -> QRect:
    """Clamp both dimensions and position, including negative screen origins."""
    width = min(max(1, rect.width()), available.width())
    height = min(max(1, rect.height()), available.height())
    x = min(max(rect.x(), available.left()), available.right() - width + 1)
    y = min(max(rect.y(), available.top()), available.bottom() - height + 1)
    return QRect(x, y, width, height)


def set_stays_on_top(widget: QWidget, on_top: bool) -> None:
    """Change the native window level in place.

    ``QWidget.setWindowFlag`` recreates the platform window and hides it, which
    shows up as a flash when pinning. Changing the flag on the existing QWindow
    only updates the NSWindow level, keeping the same window, geometry, focus,
    scroll position and selection.
    """
    handle = widget.windowHandle()
    if handle is None:
        # Nothing is on screen yet, so the widget flag cannot cause a flash.
        widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        return
    if bool(handle.flags() & Qt.WindowType.WindowStaysOnTopHint) != on_top:
        handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)


def is_stays_on_top(widget: QWidget) -> bool:
    handle = widget.windowHandle()
    flags = handle.flags() if handle is not None else widget.windowFlags()
    return bool(flags & Qt.WindowType.WindowStaysOnTopHint)


class PopupWindowController(QObject):
    """Keep geometry separate from editable app settings and translation state."""

    def __init__(self, window: QWidget, state_path: Path | None = None):
        super().__init__(window)
        self._window = weakref.ref(window)
        self.path = state_path or constants.CONFIG_DIR / "window-state.json"
        self.state = self._load()
        self.pinned = False
        self.user_sized = False
        self.reconfiguring = False
        self._prepared = False
        self._expected_size: QSize | None = None
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
        except (OSError, ValueError):
            return {}
        if not isinstance(value, dict):
            return {}
        # Earlier versions stored "pinned"; it must not make a new window stay open.
        value.pop("pinned", None)
        return value

    def _number(self, key: str, default: int) -> int:
        value = self.state.get(key)
        return value if type(value) is int and 0 < value < 100000 else default

    @property
    def preferred_width(self) -> int:
        return max(constants.POPUP_MIN_WIDTH, self._number("width", DEFAULT_WIDTH))

    @property
    def max_auto_height(self) -> int:
        return max(constants.POPUP_MIN_HEIGHT, self._number("height", DEFAULT_MAX_HEIGHT))

    def _available(self, point: QPoint) -> QRect | None:
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if not screen:
            return None
        return screen.availableGeometry().adjusted(0, 0, 0, -TITLE_BAR_ALLOWANCE)

    def prepare_show(self, initial_height: int | None = None) -> None:
        """Place a fresh panel near the pointer; keep a visible panel's frame."""
        window = self.window
        if self._prepared and window.isVisible():
            return
        cursor = QCursor.pos()
        available = self._available(cursor)
        if available is None:
            return
        width = self.preferred_width
        reserve = min(self.max_auto_height, available.height())
        # Reserve the largest automatic height so growth never needs to move the panel.
        placed = fit_to_screen(QRect(cursor + QPoint(10, 20), QSize(width, reserve)), available)
        height = min(initial_height or reserve, reserve)
        self._apply_geometry(QRect(placed.topLeft(), QSize(placed.width(), height)), available)
        self._prepared = True

    def _apply_geometry(self, rect: QRect, available: QRect) -> None:
        window = self.window
        self.reconfiguring = True
        try:
            window.setMinimumSize(
                min(constants.POPUP_MIN_WIDTH, available.width()),
                min(constants.POPUP_MIN_HEIGHT, available.height()),
            )
            self._expected_size = rect.size()
            window.setGeometry(rect)
        finally:
            self.reconfiguring = False

    def fit_height(self, desired: int, grow_only: bool = False) -> None:
        """Grow or shrink with content until the user chooses a size."""
        window = self.window
        if (
            self.user_sized
            or not self._prepared
            or not window.isVisible()
            or window.isMinimized()
            or window.isMaximized()
            or window.isFullScreen()
        ):
            return
        geometry = window.geometry()
        available = self._available(geometry.center())
        if available is None:
            return
        limit = min(self.max_auto_height, available.bottom() - geometry.top() + 1)
        height = max(window.minimumHeight(), min(desired, limit))
        if grow_only:
            height = max(height, geometry.height())
        if height != geometry.height():
            target = QRect(geometry.topLeft(), QSize(geometry.width(), height))
            self._apply_geometry(target, available)

    def set_pinned(self, pinned: bool) -> None:
        """Pin in place: no hide/show, no geometry change and no focus change."""
        self.pinned = pinned
        set_stays_on_top(self.window, pinned)

    def reassert_level(self) -> None:
        if is_stays_on_top(self.window) != self.pinned:
            set_stays_on_top(self.window, self.pinned)

    def save(self) -> None:
        self._save_timer.stop()
        window = self.window
        if not self._prepared or not self.user_sized or window.isMinimized():
            return
        if window.isMaximized() or window.isFullScreen():
            return
        rect = window.geometry()
        state = dict(self.state)
        state.update({"width": rect.width(), "height": rect.height(), "x": rect.x(), "y": rect.y()})
        self.state = state
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:
            logger.warning("Could not save window geometry: %s", error)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        window = self.window
        if (
            watched is window
            and event.type() in {QEvent.Type.Move, QEvent.Type.Resize}
            and self._prepared
            and not self.reconfiguring
            and window.isVisible()
            and not window.isMinimized()
        ):
            if event.type() == QEvent.Type.Resize:
                # Native resize notifications can arrive after our own setGeometry.
                if self._expected_size is not None and event.size() == self._expected_size:
                    return super().eventFilter(watched, event)
                self._expected_size = None
                self.user_sized = True
            if self.user_sized:
                self._save_timer.start(250)
        return super().eventFilter(watched, event)

    def _screen_removed(self, _screen) -> None:
        window = self.window
        if window is not None and window.isVisible():
            available = self._available(window.pos())
            if available is not None:
                self._apply_geometry(fit_to_screen(window.geometry(), available), available)
