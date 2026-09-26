"""Settings dialog lifecycle coordination."""

from __future__ import annotations

from collections.abc import Callable

from lingoflow.config.settings import AppSettings
from lingoflow.ui.settings_dialog import SettingsDialog


class SettingsCoordinator:
    """Own settings dialog lifecycle and settings-change delegation.

    Opening Settings leaves any reading window alone; the menu window presenter
    keeps Settings above a pinned reading window while Settings is in use.
    """

    def __init__(
        self,
        settings: AppSettings,
        on_settings_changed: Callable[[AppSettings], None],
        present: Callable[[object], None],
        dialog_factory: Callable[[AppSettings], SettingsDialog] = SettingsDialog,
    ) -> None:
        self.settings = settings
        self._on_settings_changed = on_settings_changed
        self._present = present
        self._dialog_factory = dialog_factory
        self.dialog: SettingsDialog | None = None
        self.is_open = False

    def show(self, section: str | None = None) -> None:
        """Show the settings dialog, reusing the existing one if open."""
        if not self.is_open:
            self.is_open = True
            dialog = self._dialog_factory(self.settings)
            self.dialog = dialog
            dialog.settings_changed.connect(self.apply_settings)
            dialog.finished.connect(lambda _: self.on_closed(dialog))
        if section and hasattr(self.dialog, "show_section"):
            self.dialog.show_section(section)
        self._present(self.dialog)

    def raise_current(self) -> None:
        """Raise the current settings dialog if present."""
        if self.dialog is not None:
            self._present(self.dialog)

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
