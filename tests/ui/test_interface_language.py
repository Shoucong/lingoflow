from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from lingoflow.config.settings import AppSettings
from lingoflow.i18n import current_language, set_language
from lingoflow.ui import messages, tray_controller
from lingoflow.ui.menu_windows import AboutWindow
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.settings_dialog import SettingsDialog


def test_english_is_the_default_and_older_settings_files_stay_english():
    assert AppSettings().ui.language == "en"
    legacy = AppSettings.model_validate({"ui": {"theme": "dark", "hide_on_focus_loss": True}})
    assert legacy.ui.language == "en"
    assert current_language() == "en"


def test_settings_dialog_offers_and_saves_the_interface_language(qtbot):
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    combo = dialog.interface_language_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["English", "中文"]
    assert dialog.windowTitle() == "LingoFlow Settings"
    combo.setCurrentIndex(combo.findData("zh"))
    built = dialog._build_settings_from_ui()
    assert built.ui.language == "zh"


def test_settings_dialog_is_built_in_chinese_when_chosen(qtbot):
    set_language("zh")
    settings = AppSettings()
    settings.ui.language = "zh"
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "LingoFlow 设置"
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == [
        "通用",
        "朗读",
        "模型与高级",
    ]
    assert dialog.interface_language_combo.currentData() == "zh"


def test_open_reading_window_switches_language_without_losing_state(
    qtbot, monkeypatch, tmp_path, own_popup
):
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    settings = AppSettings()
    popup = own_popup(TranslationPopup(settings, window_state_path=tmp_path / "w.json"))
    popup.show_with_text("kinase")
    popup.start_translation()
    popup.append_translation("激酶")
    popup.pin_btn.click()
    assert popup.stop_btn.text() == "Stop"
    assert popup.pin_btn.accessibleName() == "Unpin window"
    target = popup.get_target_language()

    chinese = settings.model_copy(deep=True)
    chinese.ui.language = "zh"
    set_language("zh")
    popup.update_settings(chinese)

    assert popup.stop_btn.text() == "停止"
    assert popup.pin_btn.accessibleName() == "取消固定窗口"
    assert popup.edit_action.text() == "编辑原文"
    assert popup.target_combo.currentText() == "简体中文"
    assert popup.get_target_language() == target
    assert popup.is_pinned
    assert popup.translation_text.toPlainText() == "激酶"


def test_menu_bar_about_and_notifications_follow_the_language(qtbot, monkeypatch):
    class Icon:
        def __init__(self):
            self.tooltip = ""

        def setIcon(self, _icon):  # noqa: N802
            pass

        def setToolTip(self, text):  # noqa: N802
            self.tooltip = text

        def setContextMenu(self, _menu):  # noqa: N802
            pass

        def show(self):
            pass

    monkeypatch.setattr(tray_controller, "QSystemTrayIcon", Icon)
    settings = AppSettings()
    tray = tray_controller.TrayController(
        settings, lambda: None, lambda: None, lambda: None, lambda: None, lambda: None
    )
    labels = [action.text() for action in tray.menu.actions()]
    assert "Settings…" in labels and "About LingoFlow" in labels
    assert tray.status_action.text() == "● Ready"
    assert messages.NO_TEXT_SELECTED_TITLE == "No text selected"
    about = AboutWindow(settings, ("⌥D", "⌥S"))
    qtbot.addWidget(about)
    assert about.windowTitle() == "About LingoFlow"

    set_language("zh")
    tray.update_settings(settings)
    about.update_content(settings, ("⌥D", "⌥S"))
    labels = [action.text() for action in tray.menu.actions()]
    assert "设置…" in labels and "关于 LingoFlow" in labels
    assert tray.translate_action.text().startswith("翻译选中文字")
    assert tray.status_action.text() == "● 就绪"
    assert messages.NO_TEXT_SELECTED_TITLE == "没有选中文字"
    assert about.windowTitle() == "关于 LingoFlow"
    assert "版本" in about.details.text()
