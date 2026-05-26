from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from lingoflow.config.settings import AppSettings


def test_settings_save_load_roundtrip(isolated_settings_paths: dict[str, object]) -> None:
    settings = AppSettings()
    settings.ollama.host = " http://localhost:11434/ "
    settings.translation.source_language = "English"
    settings.translation.target_language = "Japanese"
    settings.privacy.allow_content_logging = True

    settings.save()

    loaded = AppSettings.load()

    assert loaded.ollama.host == "http://localhost:11434"
    assert loaded.translation.source_language == "English"
    assert loaded.translation.target_language == "Japanese"
    assert loaded.privacy.allow_content_logging is True


def test_settings_backup_is_used_when_primary_config_is_invalid(
    isolated_settings_paths: dict[str, object],
) -> None:
    config_file = isolated_settings_paths["config_file"]
    backup_file = isolated_settings_paths["backup_file"]

    first = AppSettings()
    first.translation.target_language = "Japanese"
    first.save()

    second = AppSettings()
    second.translation.target_language = "French"
    second.save()

    config_file.write_text('{"ollama": {"host": "localhost:11434"}}', encoding="utf-8")

    loaded = AppSettings.load()

    assert backup_file.exists()
    assert loaded.translation.target_language == "Japanese"


def test_settings_invalid_primary_and_backup_fall_back_to_defaults(
    isolated_settings_paths: dict[str, object],
) -> None:
    config_file = isolated_settings_paths["config_file"]
    backup_file = isolated_settings_paths["backup_file"]
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("{not json", encoding="utf-8")
    backup_file.write_text("{also not json", encoding="utf-8")

    loaded = AppSettings.load()

    assert loaded == AppSettings()


@pytest.mark.parametrize(
    "payload",
    [
        {"ollama": {"host": "localhost:11434"}},
        {"ollama": {"model": " "}},
        {"translation": {"source_language": "Klingon"}},
        {"translation": {"target_language": "auto"}},
        {"ocr": {"language": "eng+made_up"}},
        {"ui": {"theme": "neon"}},
        {"hotkeys": {"translate": "d"}},
        {"hotkeys": {"translate": "<alt>+d", "ocr": "<alt>+d"}},
    ],
)
def test_settings_validation_rejects_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AppSettings.model_validate(payload)


def test_settings_ignore_unknown_future_fields() -> None:
    settings = AppSettings.model_validate(
        {
            "unknown_top_level": True,
            "translation": {
                "target_language": "Spanish",
                "future_field": "ignored",
            },
        }
    )

    assert settings.translation.target_language == "Spanish"
    assert not hasattr(settings, "unknown_top_level")


def test_settings_json_does_not_enable_privacy_risks_by_default() -> None:
    payload = json.loads(AppSettings().model_dump_json())

    assert payload["privacy"]["allow_content_logging"] is False
    assert payload["privacy"]["keep_ocr_captures"] is False
