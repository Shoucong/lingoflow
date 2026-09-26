from __future__ import annotations

import threading

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
                "model": "generic-chat-model",
                "context_window": 16384,
                "max_output_tokens": 4096,
                "temperature": 0.25,
                "keep_alive": 120,
                "thinking": "auto",
                "read_timeout": 90,
            },
            "translation": {"preset": "academic", "custom_prompt": "Preserve all numbers."},
            "ocr": {"review_before_translation": False, "enhance_image": False},
            # The legacy hide_on_focus_loss key still loads and is ignored.
            "ui": {"bilingual_layout": "side_by_side", "hide_on_focus_loss": False},
        }
    )
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    built = dialog._build_settings_from_ui()
    assert built is not None
    for section in ["ollama", "translation", "ocr", "ui"]:
        assert getattr(built, section) == getattr(settings, section)


def test_milmmt_controls_match_effective_profile_and_generic_model_can_restore_custom_prompt(qtbot):
    settings = AppSettings()
    settings.translation.custom_prompt = "Preserve this preference for general models."
    settings.translation.preset = "academic"
    settings.ollama.temperature = 0.8
    settings.ollama.thinking = "on"
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    assert not dialog.temperature_spin.isEnabled()
    assert not dialog.thinking_combo.isEnabled()
    assert not dialog.preset_combo.isEnabled()
    assert not dialog.custom_prompt_input.isEnabled()
    built = dialog._build_settings_from_ui()
    assert built.ollama.temperature == 0
    assert built.ollama.thinking == "off"
    assert built.translation.custom_prompt == settings.translation.custom_prompt
    dialog.model_combo.setEditText("generic-chat-model")
    assert dialog.temperature_spin.isEnabled() and dialog.custom_prompt_input.isEnabled()
    assert dialog.preset_combo.isEnabled() and dialog.thinking_combo.isEnabled()
    assert dialog.custom_prompt_input.toPlainText() == settings.translation.custom_prompt


def test_refresh_does_not_silently_replace_missing_model(qtbot) -> None:
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    dialog.model_combo.setEditText("my-chosen-model")
    dialog._active_models_task_id = 17
    dialog._on_models_refresh_finished(17, ["other-model"], "")
    assert dialog.model_combo.currentText() == "my-chosen-model"
    assert "未安装" in dialog.connection_status.text()


def test_cancel_settings_invalidates_pending_model_refresh(qtbot, monkeypatch) -> None:
    started, release = threading.Event(), threading.Event()

    class SlowClient:
        def __init__(self, **kwargs):
            pass

        def list_models(self):
            started.set()
            release.wait(2)
            return []

    monkeypatch.setattr("lingoflow.ui.settings_dialog.OllamaClient", SlowClient)
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._refresh_models()
    qtbot.waitUntil(started.is_set)
    tasks = list(dialog._network_tasks._tasks.values())
    try:
        dialog.reject()
        assert all(task.is_cancelled() for task in tasks)
        assert dialog._active_models_task_id is None
    finally:
        release.set()
        for task in tasks:
            task._thread.join(2)
