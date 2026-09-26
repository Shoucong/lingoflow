"""Small shared palette for the reading window and settings."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def colors(mode: str) -> dict[str, str]:
    dark = mode == "dark" or (
        mode == "system" and QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    )
    if dark:
        return {
            "background": "#202226",
            "text": "#f1f3f5",
            "muted": "#a7b0ba",
            "control": "#30343b",
            "border": "#4a5059",
        }
    return {
        "background": "#f8f9fb",
        "text": "#202631",
        "muted": "#5a6473",
        "control": "#ffffff",
        "border": "#cbd2dc",
    }


def apply_palette(widget, mode: str) -> None:
    theme = colors(mode)
    palette = QPalette(QApplication.palette())
    for role, name in [
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.Base, "control"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "control"),
        (QPalette.ColorRole.ButtonText, "text"),
    ]:
        palette.setColor(role, QColor(theme[name]))
    widget.setPalette(palette)
