"""Small shared palette for the reading window and settings."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def is_dark(mode: str) -> bool:
    return mode == "dark" or (
        mode == "system" and QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    )


def colors(mode: str) -> dict[str, str]:
    if is_dark(mode):
        return {
            "background": "#1f2124",
            "text": "#eceef1",
            "source": "#b9c0c9",
            "muted": "#9aa3ad",
            "control": "#2b2e33",
            "hover": "#34383e",
            "border": "#3b4047",
            "input": "#26292d",
            "accent": "#5aa2ff",
            "accent_soft": "#23364f",
            "on_accent": "#ffffff",
            "selection": "#2f6fc4",
            "danger": "#ff8a80",
        }
    return {
        "background": "#fbfbfc",
        "text": "#1d2229",
        "source": "#46505c",
        "muted": "#6b7480",
        "control": "#ffffff",
        "hover": "#eef0f3",
        "border": "#dde1e6",
        "input": "#ffffff",
        "accent": "#1f6fd6",
        "accent_soft": "#e3eefc",
        "on_accent": "#ffffff",
        "selection": "#b5d3fb",
        "danger": "#b3261e",
    }


def apply_palette(widget, mode: str) -> None:
    theme = colors(mode)
    palette = QPalette(QApplication.palette())
    for role, name in [
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.Base, "input"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "control"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Highlight, "selection"),
    ]:
        palette.setColor(role, QColor(theme[name]))
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor(theme["text"] if not is_dark(mode) else "#ffffff"),
    )
    widget.setPalette(palette)
