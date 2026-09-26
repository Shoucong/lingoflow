"""Exercise the official completion contract through the actual translation service."""

import gc
import json

import httpx
import pytest

from lingoflow.config.settings import AppSettings
from lingoflow.core.errors import TranslationCancelledError, TranslationError
from lingoflow.core.translation_profiles import MILMMT_MODEL
from lingoflow.core.translator import TranslationService
from lingoflow.infrastructure.ollama_client import OllamaClient


def make_service(handler, detector=lambda text: "English"):
    settings = AppSettings()
    settings.ollama.model = MILMMT_MODEL
    client = OllamaClient("http://ollama.test", transport=httpx.MockTransport(handler))
    return TranslationService(settings, client=client, language_detector=detector)


@pytest.mark.parametrize(
    "text,source",
    [
        ("The prediction is not experimental evidence.", "English"),
        ("これは証拠ではない。", "Japanese"),
    ],
)
def test_official_prompt_and_decoding_reach_generate_endpoint(text, source):
    detected = []

    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/api/generate"
        assert payload["raw"] is True
        assert "messages" not in payload and "system" not in payload and "think" not in payload
        assert payload["prompt"] == (
            f"Translate this from {source} to Chinese (Simplified):\n"
            f"{source}: {text}\nChinese (Simplified):"
        )
        assert payload["options"] == {
            "num_ctx": 8192,
            "num_predict": 2048,
            "temperature": 0,
            "top_k": 1,
            "repeat_penalty": 1.0,
            "stop": ["<eos>", "<end_of_turn>"],
        }
        assert payload["keep_alive"] == 300
        return httpx.Response(
            200,
            content=(
                '{"response":"这不是", "done":false}\n'
                '{"response":"实验证据。", "done":true,"done_reason":"stop"}\n'
            ).encode(),
        )

    def detect(text):
        detected.append(text)
        return source

    service = make_service(handler, detect)
    service.settings.translation.custom_prompt = "Do not insert this into the official template."
    service.settings.translation.preset = "academic"
    service.settings.ollama.temperature = 1.5
    service.settings.ollama.thinking = "on"
    chunks, checkpoints = [], []
    result = "".join(
        service.translate_stream(text, on_chunk=chunks.append, on_checkpoint=checkpoints.append)
    )
    assert result == "这不是实验证据。" == "".join(chunks)
    assert detected == [text]
    assert checkpoints[-1].completed == (result,)
    assert service.client._streams.active_count == 0


def test_explicit_source_overrides_detector_and_traditional_name_is_canonical():
    def handler(request):
        prompt = json.loads(request.content)["prompt"]
        assert prompt == (
            "Translate this from French to Chinese (Traditional):\n"
            "French: Bonjour\nChinese (Traditional):"
        )
        return httpx.Response(200, content='{"response":"你好", "done":true}\n'.encode())

    def unexpected_detection(text):
        pytest.fail("Explicit source must not use language detection")

    service = make_service(handler, unexpected_detection)
    assert "".join(service.translate_stream("Bonjour", "Chinese(Traditional)", "French")) == "你好"


@pytest.mark.parametrize(
    "text,source", [("已经是中文。", "Chinese(Simplified)"), ("12.5 ± 0.3", "English")]
)
def test_same_language_and_language_neutral_text_preserved_without_inference(text, source):
    def handler(request):
        pytest.fail("No model call needed")

    service = make_service(handler, lambda text: source)
    chunks = []
    assert "".join(service.translate_stream(text, on_chunk=chunks.append)) == text
    assert "".join(chunks) == text


def test_unrecognized_language_requires_source_selection_instead_of_guessing():
    service = make_service(
        lambda request: pytest.fail("Must not send from auto"), lambda text: None
    )
    with pytest.raises(TranslationError, match="Choose Text Source"):
        list(service.translate_stream("Unsupported source language."))


@pytest.mark.parametrize("ending", ["", '{"done":true,"done_reason":"length"}\n'])
def test_partial_completion_never_enters_resume_checkpoint(ending):
    service = make_service(
        lambda request: httpx.Response(
            200, content=('{"response":"partial", "done":false}\n' + ending).encode()
        )
    )
    checkpoints = []
    stream = service.translate_stream("Source", on_checkpoint=checkpoints.append)
    assert next(stream) == "partial"
    with pytest.raises(TranslationError):
        list(stream)
    assert checkpoints[-1].completed == ()


@pytest.mark.parametrize("response", ["null", "123", "{}"])
def test_non_text_generate_response_is_rejected(response):
    service = make_service(
        lambda request: httpx.Response(
            200, content=('{"response":' + response + ',"done":true}\n').encode()
        )
    )
    with pytest.raises(TranslationError, match="invalid text"):
        list(service.translate_stream("Source"))


def test_milmmt_resume_retries_only_failed_segment_without_chat_context():
    prompts, detected, checkpoints = [], [], []

    def handler(request):
        payload = json.loads(request.content)
        prompt = payload["prompt"]
        prompts.append(prompt)
        assert prompt.startswith("Translate this from English to Chinese (Simplified):\nEnglish: ")
        assert prompt.endswith("\nChinese (Simplified):")
        assert "Previous source context" not in prompt
        assert "Translate only the current segment" not in prompt
        if len(prompts) == 2:
            return httpx.Response(200, content=b'{"response":"partial", "done":false}\n')
        return httpx.Response(200, content=b'{"response":"complete", "done":true}\n')

    def detect(text):
        detected.append(text)
        return "English"

    service = make_service(handler, detect)
    source = " ".join(f"Paragraph {index} has exact values [12]." for index in range(300))
    with pytest.raises(TranslationError, match="Part 2"):
        list(service.translate_stream(source, on_checkpoint=checkpoints.append))
    saved = checkpoints[-1]
    assert len(saved.completed) == 1
    output = "".join(service.translate_stream(source, checkpoint=saved))
    assert "partial" not in output and output.startswith(saved.completed[0])
    assert prompts[1] == prompts[2] and prompts.count(prompts[0]) == 1
    assert len(prompts) == saved.total + 1
    assert detected == [source, source]
    delivered = [
        prompt.split("\nEnglish: ", 1)[1].rsplit("\nChinese (Simplified):", 1)[0]
        for prompt in [prompts[0], *prompts[2:]]
    ]
    assert all(len(part.encode("utf-8")) <= 2048 for part in delivered)
    assert " ".join(" ".join(delivered).split()) == " ".join(source.split())


def test_cancellation_during_detection_does_not_start_generation():
    cancelled = False

    def detect(text):
        nonlocal cancelled
        cancelled = True
        return "English"

    service = make_service(lambda request: pytest.fail("Cancelled"), detect)
    assert list(service.translate_stream("Source", cancel_check=lambda: cancelled)) == []


def test_cancel_between_generate_chunks_exits_without_active_transport():
    service = make_service(
        lambda request: httpx.Response(
            200, content=b'{"response":"first", "done":false}\n{"response":"second", "done":true}\n'
        )
    )
    cancelled = False
    stream = service.translate_stream("Source", cancel_check=lambda: cancelled)
    assert next(stream) == "first"
    cancelled = True
    service.cancel()
    try:
        assert list(stream) == []
    except TranslationCancelledError:
        pass
    assert service.client._streams.active_count == 0


def test_repeated_incomplete_raw_streams_close_nested_iterators(caplog):
    service = make_service(
        lambda request: httpx.Response(
            200, content=b'{"response":"partial", "done":true,"done_reason":"length"}\n'
        )
    )
    for _ in range(10):
        with pytest.raises(TranslationError):
            list(service.translate_stream("Source"))
    gc.collect()
    assert service.client._streams.active_count == 0
    assert "Task was destroyed" not in caplog.text
