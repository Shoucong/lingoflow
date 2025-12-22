from lingoflow.infrastructure.ollama_client import OllamaClient, OllamaConnectionError

client = OllamaClient()

# Test 1: Check if Ollama is available
print(f'Ollama available: {client.is_available()}')
print()

# Test 2: List models
try:
    models = client.list_models()
    print('Available models:')
    for m in models:
        size_gb = m.size / (1024 * 1024 * 1024)
        print(f'  - {m.name} ({size_gb:.1f} GB)')
except OllamaConnectionError as e:
    print(f'Error: {e}')
print()

# Test 3: Streaming chat
print('Streaming test:')
try:
    for chunk in client.chat_stream('Say hello in 3 languages', model='gemma3:4B'):
        print(chunk.content, end='', flush=True)
    print()  # newline at end
except Exception as e:
    print(f'Error: {e}')
print()

# Test 4: Non-streaming chat
print("None Streaming Chat test:")
try: 
    response = client.chat('Say hello in 5 languages including Chinese', model='gemma3:4B')
    print(response.content)
except Exception as e:
    print(f"Error: {e}")
print()

print("Test completed.")
