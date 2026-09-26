from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QRect

from lingoflow.config.settings import AppSettings
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.window_controller import fit_to_screen


@pytest.fixture
def make_popup(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)

    def make():
        settings = AppSettings()
        settings.ui.hide_on_focus_loss = False
        popup = TranslationPopup(settings, window_state_path=tmp_path / "window-state.json")
        qtbot.addWidget(popup)
        popup.show_with_text("Original text")
        return popup

    return make


@pytest.mark.parametrize("available", [QRect(0, 0, 1440, 900), QRect(-1920, -200, 1920, 1080)])
def test_geometry_is_visible_on_small_or_negative_origin_screen(available):
    fitted = fit_to_screen(QRect(9000, -9000, 4000, 3000), available)
    assert available.contains(fitted)
    assert fitted.size() == available.size()


def test_popup_remembers_resized_dimensions_and_pin(make_popup):
    popup = make_popup()
    popup.resize(720, 520)
    popup.pin_btn.setChecked(True)
    popup.window_controller.save()
    assert popup.width() == 720
    assert popup.height() == 520
    saved = json.loads(popup.window_controller.path.read_text())
    assert saved["pinned"] is True

    restored = make_popup()
    assert restored.size() == popup.size()
    assert restored.pin_btn.isChecked()


def test_new_translation_preserves_visible_panel_geometry(make_popup):
    popup = make_popup()
    popup.setGeometry(30, 40, 720, 520)
    geometry = popup.geometry()
    popup.show_with_text("A different source")
    assert popup.geometry() == geometry


def test_pin_and_focus_preference_control_outside_dismissal(make_popup):
    popup = make_popup()
    popup.outside_clicked.emit()
    assert popup.isVisible()
    popup.settings.ui.hide_on_focus_loss = True
    popup.pin_btn.setChecked(True)
    popup.outside_clicked.emit()
    assert popup.isVisible()
    popup.pin_btn.setChecked(False)
    popup.outside_clicked.emit()
    assert not popup.isVisible()


def test_stream_does_not_restore_minimized_panel(make_popup, qtbot):
    popup = make_popup()
    popup.start_translation()
    popup.showMinimized()
    qtbot.waitUntil(popup.isMinimized)
    popup.append_translation("Still translating")
    assert popup.isMinimized()
    assert popup.translation_text.toPlainText() == "Still translating"


def test_latest_button_clears_selection_and_resumes_reading(make_popup):
    popup = make_popup()
    popup.append_translation("A selected word")
    popup.translation_text.selectAll()
    popup.latest_btn.click()
    assert not popup.translation_text.textCursor().hasSelection()


def test_long_source_can_be_expanded_and_scrolled(make_popup):
    popup = make_popup()
    source = "A long source paragraph.\n" * 200
    popup.show_with_text(source)
    assert not popup.source_toggle.isChecked()
    popup.source_toggle.click()
    assert popup.source_text.isVisible()
    assert popup.source_text.toPlainText() == source
