"""System tray menu and notification controller."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lingoflow.config.constants import APP_ICON_FILE, APP_NAME
from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

STATUS_TEXT = {
    "Ready": "就绪",
    "Translating...": "正在翻译…",
    "Capturing...": "正在截图…",
    "Recognizing...": "正在识别文字…",
    "Reading selection...": "正在读取选中文字…",
    "Review text": "等待编辑原文",
    "Failed": "翻译失败",
    "Ollama offline": "Ollama 未运行",
    "Model unavailable": "模型不可用",
}
BUSY_STATUSES = {"Translating...", "Capturing...", "Recognizing...", "Reading selection..."}


def format_hotkey(settings: AppSettings, action: str) -> str:
    """Format a configured hotkey for display in menus."""
    if action == "translate":
        hotkey = settings.hotkeys.translate
    elif action == "ocr":
        hotkey = settings.hotkeys.ocr
    else:
        return ""

    display = hotkey.replace("<alt>", "⌥").replace("<cmd>", "⌘")
    display = display.replace("<ctrl>", "⌃").replace("<shift>", "⇧")
    display = display.replace("+", "")
    return display.upper()


class TrayController:
    """Own the menu bar icon, menu actions, status, and notifications."""

    def __init__(
        self,
        settings: AppSettings,
        on_translate: Callable[[], None],
        on_ocr: Callable[[], None],
        on_settings: Callable[[], None],
        on_about: Callable[[], None],
        on_quit: Callable[[], None],
        on_permissions: Callable[[], None] | None = None,
        on_input: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings
        self._on_translate = on_translate
        self._on_ocr = on_ocr
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_quit = on_quit
        self._on_permissions = on_permissions
        self._on_input = on_input

        self.tray_icon = QSystemTrayIcon()
        self.menu: QMenu | None = None
        self.status_action: QAction | None = None
        self.translate_action: QAction | None = None
        self.ocr_action: QAction | None = None
        self._setup()

    def _menu_action(self, name: str, callback: Callable[[], None]) -> Callable[[], None]:
        """Run a menu command on the next event-loop pass, after the menu closes.

        ``triggered`` is delivered while AppKit is still finishing the status
        item's menu tracking. Commands that activate the app and order a window
        front are therefore queued once instead of running inside that context.
        """

        def trigger(*_args) -> None:
            logger.debug("Menu action %s selected", name)
            QTimer.singleShot(0, lambda: self._run_menu_action(name, callback))

        return trigger

    @staticmethod
    def _run_menu_action(name: str, callback: Callable[[], None]) -> None:
        logger.debug("Menu action %s running", name)
        callback()

    def _setup(self) -> None:
        """Create the system tray icon and menu."""
        icon = QIcon(str(APP_ICON_FILE))
        if icon.isNull():
            logger.warning(f"Could not load app icon: {APP_ICON_FILE}")
            icon = QApplication.style().standardIcon(
                QApplication.style().StandardPixmap.SP_ComputerIcon
            )
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip(f"{APP_NAME} · 就绪")

        menu = QMenu()
        self.menu = menu
        menu.aboutToShow.connect(lambda: logger.debug("Status menu opening"))
        menu.aboutToHide.connect(lambda: logger.debug("Status menu closing"))

        self.status_action = QAction("● 就绪", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        menu.addSeparator()

        self.translate_action = QAction(self._translate_label(), menu)
        self.translate_action.triggered.connect(self._menu_action("translate", self._on_translate))
        menu.addAction(self.translate_action)

        self.ocr_action = QAction(self._ocr_label(), menu)
        self.ocr_action.triggered.connect(self._menu_action("ocr", self._on_ocr))
        menu.addAction(self.ocr_action)

        if self._on_input:
            input_action = QAction("输入文字翻译…", menu)
            input_action.triggered.connect(self._menu_action("input", self._on_input))
            menu.addAction(input_action)

        menu.addSeparator()

        settings_action = QAction("设置…", menu)
        settings_action.triggered.connect(self._menu_action("settings", self._on_settings))
        menu.addAction(settings_action)

        if self._on_permissions:
            permissions_action = QAction("权限与诊断…", menu)
            permissions_action.triggered.connect(
                self._menu_action("permissions", self._on_permissions)
            )
            menu.addAction(permissions_action)

        about_action = QAction(f"关于 {APP_NAME}", menu)
        about_action.triggered.connect(self._menu_action("about", self._on_about))
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = QAction(f"退出 {APP_NAME}", menu)
        quit_action.triggered.connect(self._menu_action("quit", self._on_quit))
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        logger.debug("System tray icon created")

    def update_settings(self, settings: AppSettings) -> None:
        """Apply settings that affect tray labels."""
        self.settings = settings
        if self.translate_action:
            self.translate_action.setText(self._translate_label())
        if self.ocr_action:
            self.ocr_action.setText(self._ocr_label())

    def update_status(self, status: str) -> None:
        """Update tray icon status."""
        text = STATUS_TEXT.get(status, status)
        marker = "◐" if status in BUSY_STATUSES else "●"
        self._set_status(f"{marker} {text}", f"{APP_NAME} · {text}")

    def show_notification(self, title: str, message: str) -> None:
        """Show a system notification."""
        if self.tray_icon and self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def hide(self) -> None:
        """Hide the tray icon."""
        self.tray_icon.hide()

    def _set_status(self, action_text: str, tooltip: str) -> None:
        """Set the visible status action and tooltip."""
        if self.status_action:
            self.status_action.setText(action_text)
        self.tray_icon.setToolTip(tooltip)

    def _translate_label(self) -> str:
        return f"翻译选中文字\t{format_hotkey(self.settings, 'translate')}"

    def _ocr_label(self) -> str:
        return f"截图识别翻译\t{format_hotkey(self.settings, 'ocr')}"
