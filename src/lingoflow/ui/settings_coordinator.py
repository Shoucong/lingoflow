"""Settings dialog lifecycle coordination."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer

from lingoflow.config.settings import AppSettings
from lingoflow.ui import messages
from lingoflow.ui.settings_dialog import SettingsDialog


class SettingsCoordinator:
    """Own settings dialog lifecycle and settings-change delegation."""

    def __init__(
        self,
        settings: AppSettings,
        on_settings_changed: Callable[[AppSettings], None],
        dismiss_popup: Callable[[str], None],
        activate_app: Callable[[], None],
        raise_dialog: Callable[[object], None],
        dialog_factory: Callable[[AppSettings], SettingsDialog] = SettingsDialog,
    ) -> None:
        self.settings = settings
        self._on_settings_changed = on_settings_changed
        self._dismiss_popup = dismiss_popup
        self._activate_app = activate_app
        self._raise_dialog = raise_dialog
        self._dialog_factory = dialog_factory
        self.dialog: SettingsDialog | None = None
        self.is_open = False

    def show(self) -> None:
        """Show the settings dialog, reusing the existing one if open."""
        if self.is_open:
            self.raise_current()
            return

        self._dismiss_popup(messages.SETTINGS_OPEN_DISMISS_POPUP_REASON)
        self.is_open = True

        dialog = self._dialog_factory(self.settings)
        self.dialog = dialog
        dialog.settings_changed.connect(self.apply_settings)
        dialog.finished.connect(lambda _: self.on_closed(dialog))

        self._activate_app()
        QTimer.singleShot(0, lambda: self._raise_dialog(dialog))
        QTimer.singleShot(150, lambda: self._raise_dialog(dialog))
        dialog.show()

    def raise_current(self) -> None:
        """Raise the current settings dialog if present."""
        self._raise_dialog(self.dialog)

    def on_closed(self, dialog: SettingsDialog) -> None:
        """Clear dialog state after a modeless settings window closes."""
        if dialog is not self.dialog:
            return

        self.dialog = None
        self.is_open = False
        dialog.deleteLater()

    def apply_settings(self, new_settings: AppSettings) -> None:
        """Record and delegate a validated settings change."""
        settings_snapshot = new_settings.model_copy(deep=True)
        self.settings = settings_snapshot
        self._on_settings_changed(settings_snapshot)

    def update_settings(self, settings: AppSettings) -> None:
        """Keep future settings dialogs in sync with app settings."""
        self.settings = settings
