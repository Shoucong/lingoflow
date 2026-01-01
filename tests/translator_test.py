from lingoflow.core.translator import TranslationService
from lingoflow.config.settings import AppSettings

settings = AppSettings()  # Creates fresh settings with NEW defaults
settings.save()  

service = TranslationService()

# Check availability
print(f'Service available: {service.is_available()}')
print(f'Available models: {service.get_available_models()[:3]}...')
print()

# Test streaming translation
print('Streaming translation test:')
print('Source: Hello, how are you today?')
print('Target: ', end='')
for chunk in service.translate_stream('Hello, how are you today?', 'Chinese (Simplified)'):
    print(chunk, end='', flush=True)
print()
print()

# Test non-streaming
print('Non-streaming translation test:')
result = service.translate('Good morning! Nice to see you!', 'Japanese')
print(f'Status: {result.status.value}')
print(f'Translation: {result.translated_text}')
print()

# Test word lookup feature
print('Word lookup test:')
print('Looking for word: "Architecture" meaning "The art and science of building design."')
print('Result: ', end='')
for chunk in service.lookup_word(
    attempt='grocrery',
    meaning='going out to buy something shopping',
    language='English'
):
    print(chunk, end='', flush=True)
print()