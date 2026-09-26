"""System tray menu and notification controller."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lingoflow.config.constants import APP_ICON_FILE, APP_NAME
from lingoflow.config.settings import AppSettings
from lingoflow.i18n import tr
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

STATUS_TEXT = {
    "Ready": ("Ready", "就绪"),
    "Translating...": ("Translating…", "正在翻译…"),
    "Capturing...": ("Capturing…", "正在截图…"),
    "Recognizing...": ("Recognizing text…", "正在识别文字…"),
    "Reading selection...": ("Reading selection…", "正在读取选中文字…"),
    "Review text": ("Editing source", "等待编辑原文"),
    "Failed": ("Translation failed", "翻译失败"),
    "Ollama offline": ("Ollama is not running", "Ollama 未运行"),
    "Model unavailable": ("Model unavailable", "模型不可用"),
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
        self._labeled: list[tuple[QAction, tuple[str, str]]] = []
        self._status = "Ready"
        self._setup()

    def _menu_action(self, name: str, callback: Callable[[], None]) -> Callable[[], None]:
        """Run a menu command on the next event-loop pass, after the menu closes.

        ``triggered`` is delivered while AppKit is still finishing the status
        item's menu tracking. Commands that activate the app and order a window
        front are therefore queued once instead of running inside that context.
        """

        def trigger(*_args) -> None:
            logger.info("trace menu: %s selected", name)
            QTimer.singleShot(0, lambda: self._run_menu_action(name, callback))

        return trigger

    @staticmethod
    def _run_menu_action(name: str, callback: Callable[[], None]) -> None:
        logger.info("trace menu: %s running after menu closed", name)
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

        menu = QMenu()
        self.menu = menu
        menu.aboutToShow.connect(lambda: logger.info("trace menu: opening"))
        menu.aboutToHide.connect(lambda: logger.info("trace menu: closing"))

        self.status_action = QAction(menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        menu.addSeparator()

        self.translate_action = QAction(menu)
        self.translate_action.triggered.connect(self._menu_action("translate", self._on_translate))
        menu.addAction(self.translate_action)

        self.ocr_action = QAction(menu)
        self.ocr_action.triggered.connect(self._menu_action("ocr", self._on_ocr))
        menu.addAction(self.ocr_action)

        if self._on_input:
            input_action = self._labeled_action(menu, "Translate Typed Text…", "输入文字翻译…")
            input_action.triggered.connect(self._menu_action("input", self._on_input))
            menu.addAction(input_action)

        menu.addSeparator()

        settings_action = self._labeled_action(menu, "Settings…", "设置…")
        settings_action.triggered.connect(self._menu_action("settings", self._on_settings))
        menu.addAction(settings_action)

        if self._on_permissions:
            permissions_action = self._labeled_action(
                menu, "Permissions && Diagnostics…"  # "&&" shows one "&", "权限与诊断…"
            )
            permissions_action.triggered.connect(
                self._menu_action("permissions", self._on_permissions)
            )
            menu.addAction(permissions_action)

        about_action = self._labeled_action(menu, f"About {APP_NAME}", f"关于 {APP_NAME}")
        about_action.triggered.connect(self._menu_action("about", self._on_about))
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = self._labeled_action(menu, f"Quit {APP_NAME}", f"退出 {APP_NAME}")
        quit_action.triggered.connect(self._menu_action("quit", self._on_quit))
        menu.addAction(quit_action)

        self.retranslate()
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        logger.debug("System tray icon created")

    def _labeled_action(self, menu: QMenu, english: str, chinese: str) -> QAction:
        action = QAction(menu)
        self._labeled.append((action, (english, chinese)))
        return action

    def retranslate(self) -> None:
        """Apply the interface language and hotkeys to every menu label."""
        for action, (english, chinese) in self._labeled:
            action.setText(tr(english, chinese))
        if self.translate_action:
            self.translate_action.setText(self._translate_label())
        if self.ocr_action:
            self.ocr_action.setText(self._ocr_label())
        self.update_status(self._status)

    def update_settings(self, settings: AppSettings) -> None:
        """Apply settings that affect tray labels (hotkeys and interface language)."""
        self.settings = settings
        self.retranslate()

    def update_status(self, status: str) -> None:
        """Update tray icon status."""
        self._status = status
        english, chinese = STATUS_TEXT.get(status, (status, status))
        text = tr(english, chinese)
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
        label = tr("Translate Selection", "翻译选中文字")
        return f"{label}\t{format_hotkey(self.settings, 'translate')}"

    def _ocr_label(self) -> str:
        label = tr("Screenshot Translate", "截图识别翻译")
        return f"{label}\t{format_hotkey(self.settings, 'ocr')}"
