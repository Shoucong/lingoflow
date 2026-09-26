from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from lingoflow.config.settings import AppSettings
from lingoflow.ui.popup import TranslationPopup


@pytest.fixture
def popup(qtbot, monkeypatch, tmp_path, own_popup) -> TranslationPopup:
    # Keep tests independent of global macOS event monitors and other windows.
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    widget = TranslationPopup(AppSettings(), window_state_path=tmp_path / "window-state.json")
    own_popup(widget)
    widget.resize(420, 320)
    widget.show_with_text("Original text")
    return widget


def shown(widget) -> bool:
    return widget.isVisibleTo(widget.window())


def test_popup_uses_readable_language_names_and_can_dismiss(qtbot, monkeypatch, own_popup):
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    settings = AppSettings()
    settings.translation.source_language = "English"
    settings.translation.target_language = "Japanese"
    popup = TranslationPopup(settings)
    own_popup(popup)

    popup.show_with_text("Hello")
    popup.append_translation("こんにちは")
    qtbot.waitUntil(lambda: "こんにちは" in popup.translation_text.toPlainText(), timeout=1000)

    assert popup.source_label.text() == "英语"
    assert popup.target_combo.currentText() == "日语"
    assert popup.get_target_language() == "Japanese"

    popup.dismiss()
    qtbot.waitUntil(lambda: not popup.isVisible(), timeout=1000)


def test_auto_source_shows_auto_until_the_language_is_identified(popup) -> None:
    assert popup.source_label.text() == "自动"
    popup.set_detected_source_language("Japanese")
    assert popup.source_label.text() == "日语"
    popup.show_with_text("Another request")
    assert popup.source_label.text() == "自动"


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


def test_actions_appear_only_for_the_current_state(popup) -> None:
    popup.start_translation()
    assert popup.status_label.text() == "正在等待模型…"
    assert shown(popup.stop_btn)
    assert not shown(popup.retry_btn)
    assert not shown(popup.copy_btn)
    assert not shown(popup.speak_translation_btn)

    popup.append_translation("译文")
    assert popup.status_label.text() == "正在翻译…"
    assert shown(popup.copy_btn)
    assert not shown(popup.speak_translation_btn)

    popup.finish_translation()
    # A finished reading has no disabled button row and no character count.
    assert popup.status_label.text() == ""
    assert not shown(popup.stop_btn)
    assert not shown(popup.retry_btn)
    assert not shown(popup.latest_btn)
    assert shown(popup.copy_btn) and shown(popup.speak_translation_btn)
    assert not popup.findChildren(type(popup.stop_btn), "closeButton")


def test_error_preserves_partial_translation(popup) -> None:
    popup.start_translation()
    popup.append_translation("Useful partial text")
    popup.show_error("Connection lost")
    assert popup.translation_text.toPlainText() == "Useful partial text"
    assert "部分译文" in popup.status_label.text()
    assert popup.status_label.toolTip() == "Connection lost"
    assert not shown(popup.stop_btn)
    assert shown(popup.retry_btn)


def test_stop_and_retry_buttons_request_work_without_changing_source(popup, qtbot) -> None:
    popup.start_translation()
    with qtbot.waitSignal(popup.stop_requested):
        popup.stop_btn.click()
    popup.stop_translation()
    assert "已停止" in popup.status_label.text()
    assert popup.retry_btn.text() == "重试"
    with qtbot.waitSignal(popup.retry_requested) as signal:
        popup.retry_btn.click()
    assert signal.args == ["Original text"]


def test_stopped_multi_part_translation_offers_to_continue(popup) -> None:
    popup.start_translation()
    popup.set_progress(0, 3)
    popup.append_translation("第一段。")
    popup.set_progress(1, 3)
    assert "第 2/3 段" in popup.status_label.text()
    popup.stop_translation()
    assert popup.retry_btn.text() == "继续翻译"


def test_copy_uses_the_displayed_translation_and_menu_offers_other_forms(popup) -> None:
    popup.start_translation()
    popup.append_translation("显示的译文")
    popup.finish_translation()
    popup.copy_btn.click()
    assert QApplication.clipboard().text() == "显示的译文"
    popup.more_menu.aboutToShow.emit()
    popup.copy_both_action.trigger()
    assert QApplication.clipboard().text() == "Original text\n\n显示的译文"
    popup.copy_source_action.trigger()
    assert QApplication.clipboard().text() == "Original text"


def test_reading_source_is_read_only_and_does_not_block_dismissal(popup) -> None:
    popup.start_translation()
    popup.append_translation("译文")
    popup.finish_translation()
    assert popup.source_text.isReadOnly()
    assert not popup.is_reviewing
    assert popup._auto_dismiss_allowed()


def test_typed_input_or_ocr_review_is_an_explicit_edit_mode(popup, qtbot) -> None:
    popup.show_with_text("OCR text with eror")
    popup.prepare_review()
    assert popup.is_reviewing
    assert not popup.source_text.isReadOnly()
    assert shown(popup.translate_btn) and shown(popup.cancel_edit_btn)
    assert not shown(popup.pin_btn)
    assert not popup._auto_dismiss_allowed()
    popup.outside_clicked.emit()
    assert popup.isVisible()

    popup.source_text.setPlainText("Corrected OCR text")
    with qtbot.waitSignal(popup.retry_requested) as signal:
        popup.translate_btn.click()
    assert signal.args == ["Corrected OCR text"]
    popup.start_translation()
    assert not popup.is_reviewing
    assert popup.source_text.isReadOnly()
    assert shown(popup.pin_btn)


def test_edit_source_from_reading_can_be_cancelled_without_losing_translation(popup) -> None:
    popup.start_translation()
    popup.append_translation("原来的译文")
    popup.finish_translation()
    popup.enter_edit_mode()
    assert popup.is_reviewing
    assert not shown(popup.text_splitter.target_panel)
    popup.source_text.setPlainText("Original text")  # unchanged: no confirmation needed
    popup._cancel_edit()
    assert not popup.is_reviewing
    assert popup.get_source_text() == "Original text"
    assert popup.translation_text.toPlainText() == "原来的译文"
    assert popup.isVisible()


def test_cancelling_modified_edits_asks_before_discarding(popup, monkeypatch) -> None:
    popup.prepare_review()
    popup.source_text.setPlainText("Unsubmitted typing")
    asked = []
    monkeypatch.setattr(popup, "_confirm_discard", lambda: asked.append(True) or False)
    popup._cancel_edit()
    assert asked and popup.isVisible() and popup.get_source_text() == "Unsubmitted typing"


def test_editing_is_unavailable_while_translating(popup) -> None:
    popup.start_translation()
    popup.enter_edit_mode()
    assert not popup.is_reviewing


def test_long_source_is_collapsed_to_an_expandable_excerpt(popup, qtbot) -> None:
    source = "A long source paragraph that keeps going.\n" * 40
    popup.show_with_text(source)
    qtbot.waitUntil(lambda: shown(popup.expand_source_btn))
    collapsed = popup.source_text.maximumHeight()
    assert collapsed < popup.source_text.document().size().height()
    popup.expand_source_btn.click()
    assert popup.expand_source_btn.text() == "收起原文"
    assert popup.source_text.maximumHeight() > collapsed
    assert popup.get_source_text() == source


def test_short_source_needs_no_expand_control(popup, qtbot) -> None:
    popup.show_with_text("kinase")
    qtbot.wait(20)
    assert not shown(popup.expand_source_btn)


def test_latest_button_appears_only_after_leaving_the_bottom(popup, qtbot) -> None:
    popup.start_translation()
    popup.append_translation("\n".join(f"Line {i}" for i in range(120)))
    scrollbar = popup.translation_text.verticalScrollBar()
    qtbot.waitUntil(lambda: scrollbar.maximum() > 0)
    scrollbar.setValue(scrollbar.maximum())
    assert not shown(popup.latest_btn)
    scrollbar.setValue(0)
    assert shown(popup.latest_btn)
    popup.latest_btn.click()
    assert scrollbar.value() == scrollbar.maximum()
    assert not shown(popup.latest_btn)


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
    popup.side_by_side_action.trigger()
    assert popup.text_splitter.orientation() == Qt.Orientation.Vertical


def test_language_change_after_typed_input_emits_translation_request(popup, qtbot) -> None:
    popup.show_with_text("")
    popup.prepare_review()
    popup.source_text.setPlainText("Typed input")
    popup.start_translation()
    popup.append_translation("输入文字")
    popup.finish_translation()
    with qtbot.waitSignal(popup.language_changed) as changed:
        popup.target_combo.setCurrentIndex(popup.target_combo.findData("Japanese"))
    assert changed.args == ["Japanese"]


def test_speech_settings_are_one_click_from_the_more_menu(popup, qtbot) -> None:
    with qtbot.waitSignal(popup.settings_requested) as requested:
        popup.speech_settings_action.trigger()
    assert requested.args == ["speech"]
