"""System tray menu and notification controller."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lingoflow.config.constants import APP_ICON_FILE, APP_NAME
from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


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
    ) -> None:
        self.settings = settings
        self._on_translate = on_translate
        self._on_ocr = on_ocr
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_quit = on_quit
        self._on_permissions = on_permissions

        self.tray_icon = QSystemTrayIcon()
        self.status_action: QAction | None = None
        self.translate_action: QAction | None = None
        self.ocr_action: QAction | None = None
        self._setup()

    def _setup(self) -> None:
        """Create the system tray icon and menu."""
        icon = QIcon(str(APP_ICON_FILE))
        if icon.isNull():
            logger.warning(f"Could not load app icon: {APP_ICON_FILE}")
            icon = QApplication.style().standardIcon(
                QApplication.style().StandardPixmap.SP_ComputerIcon
            )
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip(f"{APP_NAME} - Ready")

        menu = QMenu()

        self.status_action = QAction("● Ready", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        menu.addSeparator()

        self.translate_action = QAction(self._translate_label(), menu)
        self.translate_action.triggered.connect(self._on_translate)
        menu.addAction(self.translate_action)

        self.ocr_action = QAction(self._ocr_label(), menu)
        self.ocr_action.triggered.connect(self._on_ocr)
        menu.addAction(self.ocr_action)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._on_settings)
        menu.addAction(settings_action)

        if self._on_permissions:
            permissions_action = QAction("Setup Permissions...", menu)
            permissions_action.triggered.connect(self._on_permissions)
            menu.addAction(permissions_action)

        about_action = QAction("About", menu)
        about_action.triggered.connect(self._on_about)
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._on_quit)
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
        if status == "Ready":
            self._set_status("● Ready", f"{APP_NAME} - Ready")
        elif status == "Translating...":
            self._set_status("◐ Translating...", f"{APP_NAME} - Translating...")
        elif status == "Capturing...":
            self._set_status("◐ Capturing...", f"{APP_NAME} - Capturing...")
        elif status == "Recognizing...":
            self._set_status("◐ Recognizing...", f"{APP_NAME} - Recognizing text...")
        else:
            self._set_status(f"● {status}", f"{APP_NAME} - {status}")

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
        """Return the current translate action label."""
        return f"Translate Selection ({format_hotkey(self.settings, 'translate')})"

    def _ocr_label(self) -> str:
        """Return the current OCR action label."""
        return f"OCR Screenshot ({format_hotkey(self.settings, 'ocr')})"
