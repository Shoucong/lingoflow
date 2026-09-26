from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QEvent, QObject, QRect
from PyQt6.QtGui import QTextCursor

from lingoflow.config.settings import AppSettings
from lingoflow.infrastructure.macos.event_monitor import is_reading_exit
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.window_controller import START_HEIGHT, fit_to_screen, is_stays_on_top


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "window-state.json"


@pytest.fixture
def make_popup(qtbot, monkeypatch, state_path, own_popup):
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)

    def make(source="Original text"):
        popup = TranslationPopup(AppSettings(), window_state_path=state_path)
        own_popup(popup)
        popup.show_with_text(source)
        return popup

    return make


@pytest.mark.parametrize("available", [QRect(0, 0, 1440, 900), QRect(-1920, -200, 1920, 1080)])
def test_geometry_is_visible_on_small_or_negative_origin_screen(available):
    fitted = fit_to_screen(QRect(9000, -9000, 4000, 3000), available)
    assert available.contains(fitted)
    assert fitted.size() == available.size()


def test_legacy_pinned_state_never_pins_a_new_window(make_popup, state_path):
    state_path.write_text(json.dumps({"width": 700, "height": 500, "x": 5, "y": 5, "pinned": True}))
    popup = make_popup()
    assert popup.is_pinned is False
    assert not popup.pin_btn.isChecked()
    assert not is_stays_on_top(popup)
    assert popup.window_controller.preferred_width == 700
    assert popup.pin_btn.accessibleName() == "Pin window"


def test_pin_is_per_window_and_not_restored_after_close(make_popup, state_path, qtbot):
    popup = make_popup()
    popup.pin_btn.click()
    assert popup.is_pinned and is_stays_on_top(popup)
    popup.dismiss()
    qtbot.waitUntil(lambda: not popup.isVisible())
    if state_path.exists():
        assert "pinned" not in json.loads(state_path.read_text())

    reopened = make_popup()
    assert reopened.is_pinned is False
    assert not reopened.pin_btn.isChecked()


def test_pin_toggles_in_place_without_hiding_or_losing_reading_state(make_popup, qtbot):
    popup = make_popup()
    popup.start_translation()
    popup.append_translation("\n".join(f"Translated line {i}" for i in range(120)))
    popup.finish_translation()
    scrollbar = popup.translation_text.verticalScrollBar()
    qtbot.waitUntil(lambda: scrollbar.maximum() > 0)
    scrollbar.setValue(scrollbar.maximum() // 2)
    cursor = popup.translation_text.textCursor()
    cursor.setPosition(20)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    popup.translation_text.setTextCursor(cursor)
    geometry, native, offset = popup.geometry(), int(popup.winId()), scrollbar.value()
    hides = []
    recorder = _EventRecorder(hides)
    popup.installEventFilter(recorder)

    for index in range(20):
        popup.pin_btn.click()
        pinned = index % 2 == 0
        assert popup.is_pinned is pinned
        assert popup.pin_btn.isChecked() is pinned
        assert is_stays_on_top(popup) is pinned
        assert ("Pinned" in popup.pin_btn.toolTip()) is pinned
        assert popup.pin_btn.accessibleName() == ("Unpin window" if pinned else "Pin window")
        assert popup.isVisible()

    assert hides == []
    assert int(popup.winId()) == native
    assert popup.geometry() == geometry
    assert scrollbar.value() == offset
    reader = popup.translation_text.textCursor()
    assert (reader.anchor(), reader.position()) == (20, 5)


class _EventRecorder(QObject):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def eventFilter(self, _watched, event):  # noqa: N802
        if event.type() in {QEvent.Type.Hide, QEvent.Type.WinIdChange}:
            self.events.append(event.type())
        return False


@pytest.mark.parametrize("state", ["waiting", "streaming", "done", "stopped", "failed"])
def test_unpinned_window_closes_on_outside_click_in_every_state(make_popup, qtbot, state):
    popup = make_popup()
    popup.start_translation()
    if state != "waiting":
        popup.append_translation("部分译文")
    if state == "done":
        popup.finish_translation()
    elif state == "stopped":
        popup.stop_translation()
    elif state == "failed":
        popup.show_error("Model failed")
    with qtbot.waitSignal(popup.closed):
        popup.outside_clicked.emit()
    assert not popup.isVisible()


def test_pinned_window_stays_and_unpinning_does_not_close_it(make_popup):
    popup = make_popup()
    popup.start_translation()
    popup.pin_btn.click()
    popup.outside_clicked.emit()
    popup._handle_app_switch()
    assert popup.isVisible()
    popup.pin_btn.click()
    # The unpin click itself is inside the window; only the next outside click closes it.
    assert popup.isVisible()
    popup.outside_clicked.emit()
    assert not popup.isVisible()


def test_switching_to_another_app_closes_unpinned_window(make_popup):
    popup = make_popup()
    popup._handle_app_switch()
    assert not popup.isVisible()


def test_clicks_that_only_close_an_open_menu_do_not_close_the_window(make_popup, monkeypatch):
    popup = make_popup()
    monkeypatch.setattr(popup, "_own_menu_open", lambda: True)
    popup._handle_native_mouse()
    assert popup.isVisible()
    monkeypatch.setattr(popup, "_own_menu_open", lambda: False)
    popup._handle_native_mouse()
    assert not popup.isVisible()


def test_minimized_window_is_not_closed_by_outside_clicks(make_popup, qtbot):
    popup = make_popup()
    popup.showMinimized()
    qtbot.waitUntil(popup.isMinimized)
    popup.outside_clicked.emit()
    popup._handle_app_switch()
    assert not popup._closing


@pytest.mark.parametrize(
    ("pid", "policy", "expected"),
    [(200, 0, True), (100, 0, False), (300, 0, False), (200, 1, False), (200, 2, False)],
    ids=["other-app", "lingoflow", "reading-app", "accessory-agent", "background"],
)
def test_only_switching_to_another_regular_app_counts_as_leaving(pid, policy, expected):
    assert is_reading_exit(pid, policy, own_pid=100, reading_pid=300) is expected


def test_new_translation_preserves_visible_panel_geometry_and_pin(make_popup):
    popup = make_popup()
    popup.setGeometry(30, 40, 720, 520)
    popup.pin_btn.click()
    geometry = popup.geometry()
    popup.show_with_text("A different source")
    assert popup.geometry() == geometry
    assert popup.is_pinned


def test_window_opens_at_standard_height_and_grows_only_for_long_text(make_popup, qtbot):
    popup = make_popup("kinase")
    qtbot.wait(30)
    start = popup.height()
    assert start == START_HEIGHT
    popup.start_translation()
    popup.append_translation("激酶")
    popup.finish_translation()
    qtbot.wait(30)
    # A short translation does not make the window jump in size.
    assert popup.height() == start

    popup.show_with_text("A long paragraph")
    popup.start_translation()
    popup.append_translation("\n".join(f"很长的一段译文 {i}" for i in range(60)))
    qtbot.waitUntil(lambda: popup.height() > start, timeout=1000)
    assert popup.height() <= popup.window_controller.max_auto_height


def test_user_resize_stops_automatic_height_and_is_remembered(make_popup, state_path, qtbot):
    popup = make_popup("kinase")
    popup.resize(610, 430)
    qtbot.waitUntil(lambda: popup.window_controller.user_sized)
    popup.start_translation()
    popup.append_translation("\n".join(f"line {i}" for i in range(80)))
    qtbot.wait(30)
    assert popup.size().width() == 610 and popup.size().height() == 430
    popup.window_controller.save()
    saved = json.loads(state_path.read_text())
    assert (saved["width"], saved["height"]) == (610, 430)
    assert "pinned" not in saved


def test_stream_does_not_restore_minimized_panel(make_popup, qtbot):
    popup = make_popup()
    popup.start_translation()
    popup.showMinimized()
    qtbot.waitUntil(popup.isMinimized)
    popup.append_translation("Still translating")
    assert popup.isMinimized()
    assert popup.translation_text.toPlainText() == "Still translating"
