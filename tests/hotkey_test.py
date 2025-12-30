from lingoflow.core.hotkey import HotkeyManager, HotkeyAction
import time

def on_translate():
    print('>>> TRANSLATE triggered! <<<')

def on_ocr():
    print('>>> OCR triggered! <<<')

manager = HotkeyManager()
manager.register(HotkeyAction.TRANSLATE, '<alt>+d', on_translate)
manager.register(HotkeyAction.OCR, '<alt>+s', on_ocr)

print(f'Registered: {manager.get_registered_hotkeys()}')
print()
print('Press Alt+D or Alt+S (hold it - should only trigger once!)')
print('Press Ctrl+C to exit')

manager.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    manager.stop()
    print('Done!')