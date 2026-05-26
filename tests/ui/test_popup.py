from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from lingoflow.config.settings import AppSettings
from lingoflow.ui.popup import TranslationPopup


def test_popup_uses_configured_source_language_and_can_dismiss(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("lingoflow.ui.popup.platform.system", lambda: "Linux")
    settings = AppSettings()
    settings.translation.source_language = "English"
    settings.translation.target_language = "Japanese"
    popup = TranslationPopup(settings)
    qtbot.addWidget(popup)

    popup.show_with_text("Hello")
    popup.append_translation("こんにちは")
    qtbot.waitUntil(
        lambda: "こんにちは" in popup.translation_text.toPlainText(),
        timeout=1000,
    )

    assert popup.source_label.text() == "English"
    assert popup.get_target_language() == "Japanese"

    popup.dismiss()
    qtbot.waitUntil(lambda: not popup.isVisible(), timeout=1000)
