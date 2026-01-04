import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from lingoflow.ui.popup import TranslationPopup

app = QApplication(sys.argv)

popup = TranslationPopup()

# Show with sample text
popup.show_with_text("Hello, how are you today?")
popup.start_translation()

# Simulate streaming translation
chunks = ["你好", "，", "你", "今天", "怎么样", "？"]
delay = 200  # ms between chunks

def stream_chunk(index):
    if index < len(chunks):
        popup.append_translation(chunks[index])
        QTimer.singleShot(delay, lambda: stream_chunk(index + 1))
    else:
        popup.finish_translation()

QTimer.singleShot(500, lambda: stream_chunk(0))

# Auto-close after 5 seconds
QTimer.singleShot(20000, app.quit)

sys.exit(app.exec())