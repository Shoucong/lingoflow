"""Reusable editable source and streaming output, independent of window policy."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QSplitter, QTextEdit


class TranslationView(QSplitter):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setChildrenCollapsible(False)
        self.source = QTextEdit()
        self.source.setObjectName("sourceText")
        self.source.setAcceptRichText(False)
        self.source.setMinimumHeight(40)
        self.source.setPlaceholderText("Original text")
        self.addWidget(self.source)
        self.target = QTextEdit()
        self.target.setObjectName("translationText")
        self.target.setReadOnly(True)
        self.target.setMinimumHeight(80)
        self.target.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.addWidget(self.target)
        self.setSizes([120, 300])

    def append_output(self, text: str) -> None:
        """Append at the end while preserving the reader's selection and viewport."""
        if not text:
            return
        reader = self.target.textCursor()
        anchor, position = reader.anchor(), reader.position()
        bar = self.target.verticalScrollBar()
        offset = bar.value()
        follow = offset >= bar.maximum() - 2 and not reader.hasSelection()
        writer = QTextCursor(self.target.document())
        writer.movePosition(QTextCursor.MoveOperation.End)
        writer.insertText(text)
        reader.setPosition(anchor)
        reader.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
        self.target.setTextCursor(reader)
        bar.setValue(bar.maximum() if follow else offset)
