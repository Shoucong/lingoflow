import sys
from PyQt6.QtWidgets import QApplication
from lingoflow.ui.settings_dialog import SettingsDialog
from lingoflow.config.settings import AppSettings

app = QApplication(sys.argv)

settings = AppSettings.load()
dialog = SettingsDialog(settings)

def on_settings_changed(new_settings):
    print("Settings changed!")
    print(f"  Model: {new_settings.ollama.model}")
    print(f"  Target: {new_settings.translation.target_language}")
    print(f"  Font size: {new_settings.ui.font_size}")

dialog.settings_changed.connect(on_settings_changed)

result = dialog.exec()
print(f"Dialog result: {'Saved' if result else 'Cancelled'}")

sys.exit(0)
