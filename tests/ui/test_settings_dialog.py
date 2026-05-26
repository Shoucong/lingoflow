from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from lingoflow.config.settings import AppSettings
from lingoflow.ui.settings_dialog import SettingsDialog


def test_settings_dialog_is_modeless_and_builds_valid_settings(qtbot) -> None:
    settings = AppSettings()
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    built = dialog._build_settings_from_ui()

    assert dialog.isModal() is False
    assert built is not None
    assert built.translation.target_language == settings.translation.target_language
