from lingoflow.core.ocr import OCRService, VISION_AVAILABLE
from lingoflow.config.settings import AppSettings

print(f'Platform: macOS')
print(f'Apple Vision available: {VISION_AVAILABLE}')
print()

# Load settings and let user choose language
settings = AppSettings.load()

print("Available language options:")
print("  1. eng        - English")
print("  2. chi_sim    - Simplified Chinese")
print("  3. chi_tra    - Traditional Chinese")
print("  4. jpn        - Japanese")
print("  5. eng+chi_sim - English + Chinese (mixed)")
print()

lang_choice = input("Select language (1-5, or type code directly): ").strip()

lang_map = {
    "1": "eng",
    "2": "chi_sim",
    "3": "chi_tra", 
    "4": "jpn",
    "5": "eng+chi_sim",
}

selected_lang = lang_map.get(lang_choice, lang_choice)
settings.ocr.language = selected_lang

print(f"\nUsing language: {selected_lang}")

# Initialize with modified settings
ocr = OCRService(settings=settings)

# Show what Apple Vision languages will be used
apple_langs = ocr._get_apple_languages()
print(f"Apple Vision identifiers: {apple_langs}")
print()

# Test interactive capture
print('Select a region with text when the capture tool appears.')
input('Press Enter to start...')

result = ocr.capture_and_extract()

if result.success:
    if result.confidence:
        print(f'Confidence: {result.confidence:.1%}')
    print(f'Extracted text ({len(result.text)} chars):')
    print('-' * 40)
    print(result.text[:500] if len(result.text) > 500 else result.text)
    print('-' * 40)
else:
    print(f'Error: {result.error_message}')