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
