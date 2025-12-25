from lingoflow.infrastructure.clipboard import ClipboardManager
import time

clipboard = ClipboardManager()

# Test 1: Set and get clipboard
print('Test 1: Set and get clipboard')
clipboard.set_text('Hello from LingoFlow!')
result = clipboard.get_text()
print(f'  Set: \"Hello from LingoFlow!\"')
print(f'  Got: \"{result}\"')
print(f'  Match: {result == "Hello from LingoFlow!"}')
print()

# Test 2: Get selected text (manual test)
print('Test 2: Get selected text')
print('  1. Select text in another window.')
print('  2. Press Enter here.')
input() # Wait for Enter

print('  >>> SWITCH FOCUS BACK TO YOUR TEXT WINDOW NOW! (3 seconds...) <<<')
time.sleep(1)
print('  2...')
time.sleep(1)
print('  1...')
time.sleep(1)

# Now the script runs copy. If you switched windows, it will copy from that window.
selected = clipboard.get_selected_text()

if selected:
    print(f'  Selected text: "{selected[:50]}..."' if len(selected) > 50 else f'  Selected text: "{selected}"')
else:
    print('  No text selected (or accessibility permission needed)')