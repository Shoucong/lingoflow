"""Reusable source and streaming output panels, independent of window policy."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget


class TranslationView(QSplitter):
    """Source above (or beside) the translation; each panel has a slot for inline tools."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(9)

        self.source_panel = QWidget()
        self.source_panel.setObjectName("sourcePanel")
        source_layout = QVBoxLayout(self.source_panel)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(2)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(4)
        self.source = QTextEdit()
        self.source.setObjectName("sourceText")
        self.source.setAcceptRichText(False)
        self.source.setReadOnly(True)
        self.source.setMinimumHeight(28)
        self.source.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        source_row.addWidget(self.source, 1)
        self.source_tools = QVBoxLayout()
        self.source_tools.setContentsMargins(0, 0, 0, 0)
        self.source_tools.setSpacing(2)
        source_row.addLayout(self.source_tools)
        source_layout.addLayout(source_row, 1)
        self.source_footer = QHBoxLayout()
        self.source_footer.setContentsMargins(0, 0, 0, 0)
        source_layout.addLayout(self.source_footer)
        self.addWidget(self.source_panel)

        self.target_panel = QWidget()
        self.target_panel.setObjectName("targetPanel")
        target_layout = QVBoxLayout(self.target_panel)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        # A read-only QTextEdit that can also report clicks on links (word cards).
        self.target = QTextBrowser()
        self.target.setOpenLinks(False)
        self.target.setOpenExternalLinks(False)
        self.target.setObjectName("translationText")
        self.target.setReadOnly(True)
        self.target.setMinimumHeight(36)
        self.target.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        target_layout.addWidget(self.target, 1)
        self.addWidget(self.target_panel)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

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
