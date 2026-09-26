from __future__ import annotations

import pytest
from AppKit import NSPasteboardItem, NSPasteboardTypeString

from lingoflow.infrastructure.macos.clipboard import ClipboardManager


class Pasteboard:
    def __init__(self):
        self.text = "original clipboard"
        self.count = 0
        self.clears = 0

    def changeCount(self):  # noqa: N802
        return self.count

    def stringForType_(self, _kind):  # noqa: N802
        return self.text

    def pasteboardItems(self):  # noqa: N802
        item = NSPasteboardItem.alloc().init()
        item.setString_forType_(self.text, NSPasteboardTypeString)
        return [item]

    def clearContents(self):  # noqa: N802
        self.count += 1
        self.clears += 1
        self.text = ""

    def writeObjects_(self, items):  # noqa: N802
        self.count += 1
        self.text = items[0].stringForType_(NSPasteboardTypeString)
        return True

    def user_copy(self, text):
        self.count += 1
        self.text = text


@pytest.fixture
def manager(monkeypatch):
    board = Pasteboard()
    instance = ClipboardManager(board, copy_timeout=0.01)
    monkeypatch.setattr(instance, "_get_accessibility_selection", lambda: None)
    monkeypatch.setattr(instance, "_frontmost_pid", lambda: 10)
    return instance, board


def test_accessibility_selection_does_not_touch_clipboard(manager, monkeypatch):
    instance, board = manager
    monkeypatch.setattr(instance, "_get_accessibility_selection", lambda: "selected word")
    assert instance.get_selected_text() == "selected word"
    assert board.text == "original clipboard" and board.count == 0


def test_copy_without_new_clipboard_data_cannot_reuse_stale_content(manager, monkeypatch):
    instance, board = manager
    monkeypatch.setattr(instance, "_simulate_copy", lambda: True)
    assert instance.get_selected_text() is None
    assert board.text == "original clipboard" and board.clears == 0


def test_successful_copy_restores_original_pasteboard(manager, monkeypatch):
    instance, board = manager

    def copy():
        board.user_copy("selected word")
        return True

    monkeypatch.setattr(instance, "_simulate_copy", copy)
    assert instance.get_selected_text() == "selected word"
    assert board.text == "original clipboard"


def test_external_copy_is_not_overwritten_by_restoration(manager, monkeypatch):
    instance, board = manager

    def copy():
        board.user_copy("selected word")
        return True

    def read_while_user_copies():
        board.user_copy("new user clipboard")
        return "selected word"

    monkeypatch.setattr(instance, "_simulate_copy", copy)
    monkeypatch.setattr(instance, "get_text", read_while_user_copies)
    assert instance.get_selected_text() is None
    assert board.text == "new user clipboard" and board.clears == 0
