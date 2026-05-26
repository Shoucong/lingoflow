"""Shared pytest fixtures for LingoFlow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def isolated_settings_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    """Point persisted settings at a temp directory for one test."""
    import lingoflow.config.constants as constants
    import lingoflow.config.settings as settings_module

    config_dir = tmp_path / "Application Support" / "LingoFlow"
    config_file = config_dir / "settings.json"
    backup_file = config_dir / "settings.backup.json"
    legacy_dir = tmp_path / "legacy-config"
    legacy_file = legacy_dir / "settings.json"

    monkeypatch.setattr(constants, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(constants, "CONFIG_FILE", config_file)
    monkeypatch.setattr(constants, "CONFIG_BACKUP_FILE", backup_file)
    monkeypatch.setattr(constants, "LEGACY_CONFIG_DIR", legacy_dir)
    monkeypatch.setattr(constants, "LEGACY_CONFIG_FILE", legacy_file)

    monkeypatch.setattr(settings_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(settings_module, "CONFIG_BACKUP_FILE", backup_file)
    monkeypatch.setattr(settings_module, "LEGACY_CONFIG_FILE", legacy_file)

    return {
        "config_dir": config_dir,
        "config_file": config_file,
        "backup_file": backup_file,
        "legacy_dir": legacy_dir,
        "legacy_file": legacy_file,
    }


@pytest.fixture
def isolated_ocr_capture_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point OCR captures at a temp directory for one test."""
    import lingoflow.config.constants as constants
    import lingoflow.core.ocr as ocr_module

    capture_dir = tmp_path / "OCR Captures"
    monkeypatch.setattr(constants, "OCR_CAPTURE_DIR", capture_dir)
    monkeypatch.setattr(ocr_module, "OCR_CAPTURE_DIR", capture_dir)
    return capture_dir
