"""Consistent presentation for windows opened from the menu bar item.

LingoFlow is a menu bar (accessory) app, so a window opened from its menu must
explicitly activate the app, then show, order front and take key focus once.
A menu window floats while it is the active window: it then appears above a
pinned reading window (which sits above ordinary apps), and drops back to the
normal level as soon as the user switches to another window or application.
"""

from __future__ import annotations

import html
import platform
import weakref
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from lingoflow.config.constants import APP_NAME, APP_VERSION
from lingoflow.config.settings import AppSettings
from lingoflow.ui.window_controller import set_stays_on_top
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


def activate_application() -> None:
    """Bring this accessory app forward so its next window receives key focus."""
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication

        app = NSApplication.sharedApplication()
        if hasattr(app, "activate"):
            app.activate()
        else:  # macOS 13
            app.activateIgnoringOtherApps_(True)
    except Exception as error:
        logger.debug("Could not activate app for a menu window: %s", error)


def application_is_active() -> bool | None:
    if platform.system() != "Darwin":
        return None
    try:
        from AppKit import NSApplication

        return bool(NSApplication.sharedApplication().isActive())
    except Exception:
        return None


class MenuWindowPresenter(QObject):
    """Show, front and focus menu windows the same way, reusing open ones."""

    def __init__(self, activate_app: Callable[[], None] = activate_application):
        super().__init__()
        self._activate_app = activate_app
        self._tracked: weakref.WeakSet[QWidget] = weakref.WeakSet()

    def present(self, window: QWidget | None) -> None:
        if window is None:
            return
        try:
            if window not in self._tracked:
                window.installEventFilter(self)
                self._tracked.add(window)
            window.winId()  # create the native window so level changes happen in place
            set_stays_on_top(window, True)
            self._activate_app()
            if not window.isVisible():
                window.show()
            window.raise_()
            window.activateWindow()
            logger.info(
                "trace window: presented %s visible=%s app_active=%s",
                type(window).__name__,
                window.isVisible(),
                application_is_active(),
            )
        except RuntimeError:
            # The Qt object was deleted while a menu action was queued.
            pass

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ActivationChange and isinstance(watched, QWidget):
            if watched.isVisible():
                active = watched.isActiveWindow()
                set_stays_on_top(watched, active)
                if active:
                    watched.raise_()
                logger.info(
                    "trace window: %s active=%s app_active=%s",
                    type(watched).__name__,
                    active,
                    application_is_active(),
                )
        return super().eventFilter(watched, event)


class AboutWindow(QDialog):
    """Modeless About window that can be reopened and reused."""

    def __init__(self, settings: AppSettings, hotkeys: tuple[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"关于 {APP_NAME}")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)
        title = QLabel(f"<b style='font-size:18px'>{APP_NAME}</b>")
        layout.addWidget(title)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("好")
        buttons.accepted.connect(self.close)
        layout.addWidget(buttons)
        self.update_content(settings, hotkeys)
        self.setMinimumWidth(360)

    def update_content(self, settings: AppSettings, hotkeys: tuple[str, str]) -> None:
        translate, ocr = hotkeys
        self.details.setText(
            f"<p>版本 {APP_VERSION}</p>"
            "<p>使用本机 Ollama 模型的划词与截图翻译工具。</p>"
            f"<p>翻译模型：{html.escape(settings.ollama.model)}</p>"
            f"<p>{translate}　翻译选中文字<br>{ocr}　截图识别并翻译</p>"
        )
