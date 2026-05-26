# ruff: noqa: N802 - Qt-compatible fakes intentionally mirror camelCase APIs.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from lingoflow.config.settings import AppSettings
from lingoflow.ui import messages
from lingoflow.ui.settings_coordinator import SettingsCoordinator


class FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class FakeSettingsDialog:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.settings_changed = FakeSignal()
        self.finished = FakeSignal()
        self.shown = False
        self.deleted = False

    def show(self) -> None:
        self.shown = True

    def deleteLater(self) -> None:
        self.deleted = True


def test_settings_coordinator_opens_once_and_applies_settings(qapp) -> None:
    settings = AppSettings()
    created_dialogs: list[FakeSettingsDialog] = []
    dismissed_reasons: list[str] = []
    activated_count = 0
    raised_dialogs: list[object] = []
    applied_settings: list[AppSettings] = []

    def make_dialog(dialog_settings: AppSettings) -> FakeSettingsDialog:
        dialog = FakeSettingsDialog(dialog_settings)
        created_dialogs.append(dialog)
        return dialog

    def activate() -> None:
        nonlocal activated_count
        activated_count += 1

    coordinator = SettingsCoordinator(
        settings=settings,
        on_settings_changed=applied_settings.append,
        dismiss_popup=dismissed_reasons.append,
        activate_app=activate,
        raise_dialog=raised_dialogs.append,
        dialog_factory=make_dialog,
    )

    coordinator.show()
    coordinator.show()

    assert len(created_dialogs) == 1
    assert created_dialogs[0].shown is True
    assert coordinator.is_open is True
    assert dismissed_reasons == [messages.SETTINGS_OPEN_DISMISS_POPUP_REASON]
    assert activated_count == 1
    assert raised_dialogs[-1] is created_dialogs[0]

    new_settings = settings.model_copy(deep=True)
    new_settings.translation.target_language = "Japanese"
    created_dialogs[0].settings_changed.emit(new_settings)

    assert coordinator.settings is not new_settings
    assert coordinator.settings == new_settings
    assert applied_settings == [coordinator.settings]

    created_dialogs[0].finished.emit(0)

    assert coordinator.is_open is False
    assert coordinator.dialog is None
    assert created_dialogs[0].deleted is True
