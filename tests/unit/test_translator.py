from __future__ import annotations

from collections.abc import Iterator

from lingoflow.config.settings import AppSettings
from lingoflow.core.translator import (
    TranslationService,
    TranslationStatus,
)
from lingoflow.infrastructure.ollama_client import (
    OllamaConnectionError,
    OllamaStreamChunk,
)


class FakeOllamaClient:
    def __init__(
        self,
        chunks: list[OllamaStreamChunk] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    def chat_stream(
        self,
        message: str,
        model: str,
        system_prompt: str | None = None,
        cancel_check=None,
    ) -> Iterator[OllamaStreamChunk]:
        self.calls.append(
            {
                "message": message,
                "model": model,
                "system_prompt": system_prompt,
            }
        )
        if self.error:
            raise self.error
        for chunk in self.chunks:
            if cancel_check and cancel_check():
                return
            yield chunk


def service_with_fake_client(fake_client: FakeOllamaClient) -> TranslationService:
    settings = AppSettings()
    settings.translation.source_language = "English"
    settings.translation.target_language = "Japanese"
    service = TranslationService(settings)
    service.client = fake_client
    return service


def test_translate_stream_uses_settings_languages_and_model() -> None:
    fake_client = FakeOllamaClient(
        [
            OllamaStreamChunk(content="こん", done=False),
            OllamaStreamChunk(content="にちは", done=True),
        ]
    )
    service = service_with_fake_client(fake_client)

    chunks = list(service.translate_stream("Hello"))

    assert "".join(chunks) == "こんにちは"
    assert fake_client.calls[0]["model"] == service.settings.ollama.model
    assert "from English to Japanese" in str(fake_client.calls[0]["message"])
    assert "Hello" in str(fake_client.calls[0]["message"])


def test_translate_auto_source_uses_auto_prompt() -> None:
    fake_client = FakeOllamaClient([OllamaStreamChunk(content="hola", done=True)])
    service = service_with_fake_client(fake_client)

    result = service.translate("hello", target_language="Spanish", source_language="auto")

    assert result.status == TranslationStatus.COMPLETED
    assert result.translated_text == "hola"
    assert "Translate the following text to Spanish" in str(fake_client.calls[0]["message"])
    assert "from auto" not in str(fake_client.calls[0]["message"])


def test_translate_returns_error_result_for_ollama_error() -> None:
    fake_client = FakeOllamaClient(error=OllamaConnectionError("offline"))
    service = service_with_fake_client(fake_client)

    result = service.translate("hello")

    assert result.status == TranslationStatus.ERROR
    assert result.translated_text == ""
    assert "offline" in str(result.error_message)


def test_translate_stream_stops_when_external_cancel_check_is_true() -> None:
    fake_client = FakeOllamaClient([OllamaStreamChunk(content="unused", done=False)])
    service = service_with_fake_client(fake_client)

    chunks = list(service.translate_stream("hello", cancel_check=lambda: True))

    assert chunks == []
