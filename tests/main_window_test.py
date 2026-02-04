import sys
import os

# Suppress Qt ICC profile warnings (harmless but noisy)
os.environ["QT_LOGGING_RULES"] = "qt.gui.icc=false"
import signal

# Allow Ctrl+C to terminate the app (PyQt blocks SIGINT by default)
signal.signal(signal.SIGINT, signal.SIG_DFL)

from PyQt6.QtWidgets import QApplication
from lingoflow.ui.main_window import MainController

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

controller = MainController()
controller.start()
print("LingoFlow is running in the system tray!")
print("Try:")
print("  - Option+D to translate selected text")
print("  - Option+S for OCR screenshot")
print("  - Click tray icon for menu")
print()
print("Press Ctrl+C in terminal to quit (or use tray menu)")

sys.exit(app.exec())