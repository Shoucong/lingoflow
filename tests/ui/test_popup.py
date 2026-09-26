from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtGui import QTextCursor

from lingoflow.config.settings import AppSettings
from lingoflow.ui.popup import TranslationPopup


@pytest.fixture
def popup(qtbot, monkeypatch, tmp_path) -> TranslationPopup:
    # Keep tests independent of global macOS event monitors and other windows.
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    settings = AppSettings()
    settings.ui.hide_on_focus_loss = False
    widget = TranslationPopup(settings, window_state_path=tmp_path / "window-state.json")
    qtbot.addWidget(widget)
    widget.resize(420, 320)
    widget.show_with_text("Original text")
    return widget


def test_popup_uses_configured_source_language_and_can_dismiss(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
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


@pytest.mark.parametrize(
    ("anchor", "position"),
    [(0, 0), (5, 5), (6, 11), (11, 6), (6, -1), (-1, 6), (0, -1), (-1, 0)],
    ids=[
        "caret-at-start",
        "caret-in-middle",
        "forward-selection",
        "backward-selection",
        "selection-to-end",
        "selection-from-end",
        "select-all",
        "select-all-backwards",
    ],
)
def test_stream_appends_without_changing_caret_or_selection(popup, anchor, position) -> None:
    original = "Hello world\n中文 🧬"
    popup.append_translation(original)
    document_end = popup.translation_text.document().characterCount() - 1
    anchor = document_end if anchor == -1 else anchor
    position = document_end if position == -1 else position
    cursor = popup.translation_text.textCursor()
    cursor.setPosition(anchor)
    cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
    popup.translation_text.setTextCursor(cursor)
    selected_text = cursor.selectedText()

    for chunk in [" next", "\n新的译文 🧪", " done"]:
        popup.append_translation(chunk)
        original += chunk
        cursor = popup.translation_text.textCursor()
        assert popup.translation_text.toPlainText() == original
        assert popup._translated_text == original
        assert (cursor.anchor(), cursor.position()) == (anchor, position)
        assert cursor.selectedText() == selected_text


@pytest.mark.parametrize("scroll_fraction", [0.0, 0.5, 1.0], ids=["top", "middle", "bottom"])
def test_stream_follows_only_when_already_at_bottom(popup, qtbot, scroll_fraction) -> None:
    popup.append_translation("\n".join(f"Original line {i}" for i in range(80)))
    scrollbar = popup.translation_text.verticalScrollBar()
    qtbot.waitUntil(lambda: scrollbar.maximum() > 0)
    old_maximum = scrollbar.maximum()
    old_position = int(old_maximum * scroll_fraction)
    scrollbar.setValue(old_position)

    popup.append_translation("\nNew line\nAnother new line")

    qtbot.waitUntil(lambda: scrollbar.maximum() > old_maximum)
    expected = scrollbar.maximum() if scroll_fraction == 1.0 else old_position
    assert scrollbar.value() == expected


def test_selection_at_end_pauses_following_until_cleared(popup, qtbot) -> None:
    popup.append_translation("\n".join(f"Original line {i}" for i in range(80)))
    scrollbar = popup.translation_text.verticalScrollBar()
    qtbot.waitUntil(lambda: scrollbar.maximum() > 0)
    cursor = popup.translation_text.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
    popup.translation_text.setTextCursor(cursor)
    selected_text = cursor.selectedText()
    scrollbar.setValue(scrollbar.maximum())
    old_position = scrollbar.value()

    popup.append_translation("\nNew line\nAnother new line")

    qtbot.waitUntil(lambda: scrollbar.maximum() > old_position)
    assert scrollbar.value() == old_position
    assert popup.translation_text.textCursor().selectedText() == selected_text

    cursor = popup.translation_text.textCursor()
    cursor.clearSelection()
    popup.translation_text.setTextCursor(cursor)
    scrollbar.setValue(scrollbar.maximum())
    old_maximum = scrollbar.maximum()
    popup.append_translation("\nLatest line")

    qtbot.waitUntil(lambda: scrollbar.maximum() > old_maximum)
    assert scrollbar.value() == scrollbar.maximum()


def test_source_selection_preserves_literal_text_during_streaming(popup) -> None:
    source = "Read <b>this word</b> & keep the notation."
    popup.show_with_text(source)
    cursor = popup.source_text.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    popup.source_text.setTextCursor(cursor)

    popup.append_translation("译文开始")
    popup.append_translation("，继续输出。")

    assert popup.source_text.textCursor().selectedText() == source
    assert popup.get_source_text() == source


def test_retry_clears_old_selection_and_follows_new_translation(popup, qtbot) -> None:
    popup.append_translation("\n".join(f"Old line {i}" for i in range(80)))
    cursor = popup.translation_text.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    popup.translation_text.setTextCursor(cursor)
    popup.clear_translation()
    replacement = "\n".join(f"New line {i}" for i in range(80))

    popup.append_translation(replacement)

    scrollbar = popup.translation_text.verticalScrollBar()
    qtbot.waitUntil(lambda: scrollbar.maximum() > 0)
    assert popup.translation_text.toPlainText() == replacement
    assert popup._translated_text == replacement
    assert not popup.translation_text.textCursor().hasSelection()
    assert scrollbar.value() == scrollbar.maximum()


def test_error_preserves_partial_translation(popup) -> None:
    popup.start_translation()
    popup.append_translation("Useful partial text")
    popup.show_error("Connection lost")
    assert popup.translation_text.toPlainText() == "Useful partial text"
    assert "partial" in popup.status_label.text()
    assert popup.status_label.toolTip() == "Connection lost"
    assert not popup.stop_btn.isEnabled()


def test_stop_and_retry_buttons_request_work_without_changing_source(popup, qtbot) -> None:
    popup.start_translation()
    with qtbot.waitSignal(popup.stop_requested):
        popup.stop_btn.click()
    popup.stop_translation()
    assert "Stopped" in popup.status_label.text()
    with qtbot.waitSignal(popup.retry_requested) as signal:
        popup.retry_btn.click()
    assert signal.args == ["Original text"]


def test_review_edits_are_used_for_retry_and_preserve_original(popup, qtbot) -> None:
    popup.prepare_review()
    popup.source_text.setPlainText("Corrected OCR text")
    assert popup.is_reviewing
    assert not popup._auto_dismiss_allowed()
    with qtbot.waitSignal(popup.retry_requested) as signal:
        popup.retry_btn.click()
    assert signal.args == ["Corrected OCR text"]
    popup.start_translation()
    assert popup.source_text.isReadOnly()
    popup.append_translation("校正后的译文")
    popup.finish_translation()
    popup.source_text.setPlainText("Another correction")
    assert "Source edited" in popup.status_label.text()
    assert not popup._status_clear_timer.isActive()
    popup._restore_source()
    assert popup.get_source_text() == "Original text"


def test_appearance_settings_change_palette_and_reading_layout(popup) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette

    settings = popup.settings.model_copy(deep=True)
    settings.ui.theme = "light"
    settings.ui.bilingual_layout = "side_by_side"
    popup.update_settings(settings)
    light = popup.palette().color(QPalette.ColorRole.Window)
    assert popup.text_splitter.orientation() == Qt.Orientation.Horizontal
    settings.ui.theme = "dark"
    popup.update_settings(settings)
    dark = popup.palette().color(QPalette.ColorRole.Window)
    assert dark.lightness() < light.lightness()


def test_language_change_after_typed_input_emits_translation_request(popup, qtbot) -> None:
    popup.show_with_text("")
    popup.prepare_review()
    popup.source_text.setPlainText("Typed input")
    popup.start_translation()
    popup.append_translation("输入文字")
    popup.finish_translation()
    with qtbot.waitSignal(popup.language_changed) as changed:
        popup.target_combo.setCurrentText("Japanese")
    assert changed.args == ["Japanese"]
