from __future__ import annotations

import json

import httpx
import pytest

from lingoflow.infrastructure.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaModelError,
    OllamaTimeoutError,
)


def client_for(handler) -> OllamaClient:
    return OllamaClient(
        host="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )


def test_is_available_returns_true_for_tags_200() -> None:
    client = client_for(lambda request: httpx.Response(200, json={"models": []}))

    assert client.is_available() is True


def test_is_available_returns_false_for_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert client_for(handler).is_available() is False


def test_list_models_maps_ollama_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "model-a",
                        "size": 123,
                        "modified_at": "2026-05-26T00:00:00Z",
                    }
                ]
            },
        )

    models = client_for(handler).list_models()

    assert len(models) == 1
    assert models[0].name == "model-a"
    assert models[0].size == 123


def test_chat_sends_non_streaming_payload_and_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert payload["stream"] is False
        assert payload["model"] == "model-a"
        assert payload["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={
                "model": "model-a",
                "message": {"content": "translated"},
                "done": True,
                "total_duration": 10,
                "eval_count": 2,
            },
        )

    response = client_for(handler).chat(
        "hello",
        model="model-a",
        system_prompt="translate",
    )

    assert response.content == "translated"
    assert response.model == "model-a"
    assert response.done is True
    assert response.eval_count == 2


def test_chat_stream_yields_chunks_and_done_marker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(
            200,
            content=(
                b'{"message": {"content": "one"}, "done": false}\n'
                b'{"message": {"content": " two"}, "done": false}\n'
                b'{"done": true}\n'
            ),
        )

    chunks = list(client_for(handler).chat_stream("hello", model="model-a"))

    assert [chunk.content for chunk in chunks] == ["one", " two", ""]
    assert chunks[-1].done is True


def test_chat_stream_cancellation_stops_before_yielding_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"message": {"content": "unused"}, "done": false}\n',
        )

    chunks = list(
        client_for(handler).chat_stream(
            "hello",
            model="model-a",
            cancel_check=lambda: True,
        )
    )

    assert chunks == []


def test_404_chat_status_maps_to_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    with pytest.raises(OllamaModelError):
        client_for(handler).chat("hello", model="missing-model")


def test_http_error_maps_to_ollama_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, request=request)

    with pytest.raises(OllamaError, match="502"):
        client_for(handler).list_models()


def test_connect_error_maps_to_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(OllamaConnectionError):
        client_for(handler).list_models()


def test_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OllamaTimeoutError):
        client_for(handler).chat("hello", model="model-a")


def test_invalid_json_maps_to_ollama_error() -> None:
    client = client_for(lambda request: httpx.Response(200, content=b"not json"))

    with pytest.raises(OllamaError, match="invalid JSON"):
        client.chat("hello", model="model-a")


@pytest.mark.parametrize(
    "body",
    [
        b'{"message":{"content":"partial"},"done":false}\n',
        b'{"error":"model failure"}\n',
        b"not-json\n",
        b"[]\n",
        b'{"message":null,"done":true}\n',
        b'{"message":{"content":1},"done":true}\n',
        b'{"done":"true"}\n',
        b'{"done":true,"done_reason":"length"}\n',
    ],
)
def test_invalid_or_incomplete_stream_cannot_succeed(body: bytes) -> None:
    client = client_for(lambda request: httpx.Response(200, content=body))
    with pytest.raises(OllamaError):
        list(client.chat_stream("source", "model-a"))


def test_output_limit_keeps_last_text_before_reporting_incomplete() -> None:
    client = client_for(
        lambda request: httpx.Response(
            200, content=b'{"message":{"content":"partial"},"done":true,"done_reason":"length"}\n'
        )
    )
    stream = client.chat_stream("source", "model-a")
    assert next(stream).content == "partial"
    with pytest.raises(OllamaError, match="incomplete"):
        next(stream)


def test_stream_stops_at_first_completion_marker() -> None:
    client = client_for(
        lambda request: httpx.Response(200, content=b'{"done":true}\nnot-another-frame\n')
    )
    assert list(client.chat_stream("source", "model-a"))[-1].done


@pytest.mark.parametrize("supports_thinking", [True, False])
def test_model_controls_reach_api_without_unsupported_thinking(supports_thinking):
    payloads = []

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": (
                        ["completion", "thinking"] if supports_thinking else ["completion"]
                    )
                },
            )
        payloads.append(json.loads(request.content))
        return httpx.Response(200, content=b'{"done":true}\n')

    client = client_for(handler)
    list(
        client.chat_stream(
            "source",
            "model",
            options={"num_ctx": 8192, "num_predict": 512, "temperature": 0.1},
            keep_alive=60,
            think=False,
        )
    )
    assert payloads[0]["options"]["num_predict"] == 512
    assert payloads[0]["keep_alive"] == 60
    assert ("think" in payloads[0]) is supports_thinking
