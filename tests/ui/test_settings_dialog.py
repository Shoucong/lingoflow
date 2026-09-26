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


def test_model_review_and_layout_settings_round_trip(qtbot) -> None:
    settings = AppSettings.model_validate(
        {
            "ollama": {
                "context_window": 16384,
                "max_output_tokens": 4096,
                "temperature": 0.25,
                "keep_alive": 120,
                "thinking": "auto",
                "read_timeout": 90,
            },
            "translation": {"preset": "academic", "custom_prompt": "Preserve all numbers."},
            "ocr": {"review_before_translation": False, "enhance_image": False},
            "ui": {"bilingual_layout": "side_by_side", "hide_on_focus_loss": False},
        }
    )
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    built = dialog._build_settings_from_ui()
    assert built is not None
    for section in ["ollama", "translation", "ocr", "ui"]:
        assert getattr(built, section) == getattr(settings, section)


def test_refresh_does_not_silently_replace_missing_model(qtbot) -> None:
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    dialog.model_combo.setEditText("my-chosen-model")
    dialog._active_models_task_id = 17
    dialog._on_models_refresh_finished(17, ["other-model"], "")
    assert dialog.model_combo.currentText() == "my-chosen-model"
    assert "missing" in dialog.connection_status.text()
