from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QDialog

from lingoflow.config.settings import AppSettings
from lingoflow.ui import tray_controller
from lingoflow.ui.menu_windows import AboutWindow, MenuWindowPresenter
from lingoflow.ui.window_controller import is_stays_on_top


def test_presenter_activates_once_per_request_and_reuses_the_window(qtbot):
    activations = []
    presenter = MenuWindowPresenter(lambda: activations.append(True))
    about = AboutWindow(AppSettings(), ("⌥D", "⌥S"))
    qtbot.addWidget(about)

    presenter.present(about)
    assert about.isVisible()
    # A menu window floats while presented so a pinned reading window cannot cover it.
    assert is_stays_on_top(about)
    presenter.present(about)
    assert activations == [True, True]

    about.close()
    assert not about.isVisible()
    presenter.present(about)
    assert about.isVisible()


def test_about_shows_version_model_and_configured_hotkeys(qtbot):
    settings = AppSettings()
    about = AboutWindow(settings, ("⌥D", "⌥S"))
    qtbot.addWidget(about)
    text = about.details.text()
    assert "⌥D" in text and "⌥S" in text
    assert "MiLMMT" in text
    assert not about.isModal()
    assert isinstance(about, QDialog)


def test_menu_commands_run_once_after_the_menu_closes(qtbot, monkeypatch):
    class Icon:
        def __init__(self):
            self.menu = None

        def setIcon(self, _icon):  # noqa: N802
            pass

        def setToolTip(self, _text):  # noqa: N802
            pass

        def setContextMenu(self, menu):  # noqa: N802
            self.menu = menu

        def show(self):
            pass

    monkeypatch.setattr(tray_controller, "QSystemTrayIcon", Icon)
    calls = []
    tray = tray_controller.TrayController(
        AppSettings(),
        on_translate=lambda: calls.append("translate"),
        on_ocr=lambda: calls.append("ocr"),
        on_settings=lambda: calls.append("settings"),
        on_about=lambda: calls.append("about"),
        on_quit=lambda: calls.append("quit"),
    )
    about = next(a for a in tray.menu.actions() if a.text().startswith("关于"))
    about.trigger()
    # Not inside AppKit's menu tracking callback...
    assert calls == []
    qtbot.waitUntil(lambda: calls == ["about"], timeout=500)
    qtbot.wait(20)
    assert calls == ["about"]
    assert tray.translate_action.text().startswith("翻译选中文字")
