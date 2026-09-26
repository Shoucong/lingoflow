"""
Ollama API client with streaming support.

Handles all communication with the local Ollama server.
"""

import json
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Optional

import httpx

from lingoflow.config.constants import (
    OLLAMA_CHAT_ENDPOINT,
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_READ_TIMEOUT,
    OLLAMA_TAGS_ENDPOINT,
)
from lingoflow.core.errors import (
    ProviderConnectionError,
    ProviderModelError,
    ProviderTimeoutError,
    TranslationCancelledError,
    TranslationError,
)
from lingoflow.core.models import ModelChunk, ModelInfo, ModelResponse
from lingoflow.infrastructure.async_stream import AsyncStreamRunner, RequestCancelledError
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

# Preserve the adapter's public names while sharing portable domain types.
OllamaResponse = ModelResponse
OllamaStreamChunk = ModelChunk
OllamaModel = ModelInfo
OllamaError = TranslationError
OllamaCancelledError = TranslationCancelledError
OllamaConnectionError = ProviderConnectionError
OllamaModelError = ProviderModelError
OllamaTimeoutError = ProviderTimeoutError


def create_ollama_client(settings):
    return OllamaClient(host=settings.ollama.host, read_timeout=settings.ollama.read_timeout)


class OllamaClient:
    """
    Client for interacting with the Ollama API.

    Supports both streaming and non-streaming requests.

    Example:
        client = OllamaClient()

        # Streaming
        for chunk in client.chat_stream("hello", model="qwen3:8B"):
            print(chunk.content, end="", flush=True)
        # Non-streaming
        response = client.chat("hello", model="qwen3:8B")
        print(response.content)
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        transport: Optional[httpx.BaseTransport] = None,
        read_timeout: float = OLLAMA_READ_TIMEOUT,
    ):
        """
        Initialize the Ollama client.

        Args:
            host: Ollama server URL
            transport: Optional httpx transport for tests.
        """
        self.host = host.rstrip("/")
        self._transport = transport
        self._streams = AsyncStreamRunner()
        self._capabilities = {}
        self._timeout = httpx.Timeout(
            connect=OLLAMA_CONNECT_TIMEOUT,
            read=read_timeout,
            write=10.0,
            pool=5.0,
        )
        logger.debug(f"OllamaClient initialized with host; {self.host}")

    # ===========================================================
    # Public Methods
    # ===========================================================

    def cancel(self) -> None:
        """Interrupt pending I/O, including before the first output token."""
        self._streams.cancel_all()

    def chat_stream(
        self,
        message: str,
        model: str,
        system_prompt: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        *,
        options: dict | None = None,
        keep_alive: int | None = None,
        think: bool | None = None,
        raw: bool = False,
    ) -> Iterator[OllamaStreamChunk]:
        try:
            yield from self._streams.iterate(
                lambda: self._chat_stream_async(
                    message,
                    model,
                    system_prompt,
                    cancel_check,
                    options,
                    keep_alive,
                    think,
                    raw,
                )
            )
        except RequestCancelledError as error:
            raise OllamaCancelledError("Translation was stopped.") from error

    async def _chat_stream_async(
        self,
        message: str,
        model: str,
        system_prompt: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        options: dict | None = None,
        keep_alive: int | None = None,
        think: bool | None = None,
        raw: bool = False,
    ) -> AsyncIterator[OllamaStreamChunk]:
        """
        Send a chat message and stream the response.

        Args:
            message: User message to send
            model: Model name to use
            system_prompt: Optional system prompt for context

        Yields:
            OllamaStreamChunk for each piece of the response

        Raises:
            OllamaConnectionError: if cannot connect to server
            OllamaTimeoutError: if request times out
            OllamaError: for other API errors
        """
        url = f"{self.host}{'/api/generate' if raw else OLLAMA_CHAT_ENDPOINT}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if raw:
            if system_prompt:
                raise OllamaError("Raw completion cannot include a system prompt.")
            payload = {"model": model, "prompt": message, "raw": True, "stream": True}

        if options is not None:
            payload["options"] = options
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        logger.debug(f"Starting streaming chat with model: {model}")
        logger.debug(f"Message length: {len(message)} chars")

        try:
            if cancel_check and cancel_check():
                return
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, trust_env=False
            ) as client:
                if think is not None:
                    cached = self._capabilities.get(model)
                    if cached and time.monotonic() - cached[0] < 60:
                        capabilities = cached[1]
                    else:
                        metadata = await client.post(f"{self.host}/api/show", json={"model": model})
                        self._raise_for_status(metadata, model=model)
                        try:
                            capabilities = metadata.json().get("capabilities", [])
                        except (ValueError, AttributeError) as error:
                            raise OllamaError("Invalid model metadata from Ollama.") from error
                        if not isinstance(capabilities, list):
                            raise OllamaError("Invalid model capabilities from Ollama.")
                        self._capabilities[model] = (time.monotonic(), capabilities)
                    if "thinking" in capabilities:
                        payload["think"] = think
                    elif think:
                        raise OllamaModelError("This model does not advertise thinking support.")
                async with client.stream("POST", url, json=payload) as response:
                    self._raise_for_status(response, model=model)

                    saw_done = False
                    async for line in response.aiter_lines():
                        if cancel_check and cancel_check():
                            return
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as error:
                            raise OllamaError("Ollama returned an invalid stream frame.") from error
                        content, done, reason = self._parse_frame(data, raw=raw)
                        if content:
                            yield OllamaStreamChunk(content=content, done=False)
                        if done:
                            if reason not in {None, "", "stop"}:
                                raise OllamaError(
                                    "Translation is incomplete (generation ended: "
                                    f"{reason}). Increase the output budget or retry."
                                )
                            saw_done = True
                            yield OllamaStreamChunk(content="", done=True, done_reason=reason)
                            break
                    if not saw_done and not (cancel_check and cancel_check()):
                        raise OllamaError(
                            "Connection ended before translation completed. "
                            "Partial output retained."
                        )
        except (OllamaConnectionError, OllamaTimeoutError, OllamaModelError, OllamaError):
            raise
        except httpx.RequestError as e:
            self._raise_request_error(e)

    def chat(
        self,
        message: str,
        model: str,
        system_prompt: Optional[str] = None,
    ) -> OllamaResponse:
        """
        Send a chat message and get the complete response.

        For UI use, prefer previous streaming method for better UX.

        Args:
            message: User message to send
            model: Model name to use
            system_prompt: Optional system prompt for context

        Returns:
            OllamaResponse with the complete response
        """
        url = f"{self.host}{OLLAMA_CHAT_ENDPOINT}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        logger.debug(f"Starting non-streaming chat request to model: {model}")

        try:
            with self._new_client() as client:
                response = client.post(url, json=payload)
                self._raise_for_status(response, model=model)
                try:
                    data = response.json()
                except ValueError as e:
                    raise OllamaError("Ollama returned an invalid JSON response.") from e

                content, done, reason = self._parse_frame(data)
                if not done or reason not in {None, "", "stop"}:
                    raise OllamaError("Ollama returned an incomplete response.")
                return OllamaResponse(
                    content=content,
                    model=data.get("model", model),
                    done=True,
                    total_duration=data.get("total_duration"),
                    eval_count=data.get("eval_count"),
                )

        except (OllamaConnectionError, OllamaTimeoutError, OllamaModelError, OllamaError):
            raise
        except httpx.RequestError as e:
            self._raise_request_error(e)

    def list_models(self) -> list[OllamaModel]:
        """
        Get list of available models from Ollama.

        Returns:
            List of OllamaModel objects
        Raise:
            OllamaConnectionError: if cannot connect to server
        """
        url = f"{self.host}{OLLAMA_TAGS_ENDPOINT}"

        logger.debug("Fetching available models")

        try:
            with self._new_client() as client:
                response = client.get(url, timeout=3.0)
                self._raise_for_status(response)
                try:
                    data = response.json()
                except ValueError as e:
                    raise OllamaError("Ollama returned an invalid JSON response.") from e

                models = [
                    OllamaModel(
                        name=m.get("name", ""),
                        size=m.get("size", 0),
                        modified_at=m.get("modified_at", ""),
                    )
                    for m in data.get("models", [])
                ]

                logger.info(f"Found {len(models)} available models")
                return models
        except (OllamaConnectionError, OllamaTimeoutError, OllamaModelError, OllamaError):
            raise
        except httpx.RequestError as e:
            self._raise_request_error(e)

    def is_available(self) -> bool:
        """
        Check if Ollama server is reachable.

        Returns:
            True if server responds, False otherwise
        """
        try:
            with self._new_client() as client:
                response = client.get(f"{self.host}/api/tags", timeout=1.5)
                return response.status_code == 200
        except Exception:
            return False

    def check_model_exists(self, model: str) -> bool:
        """
        Check if a specific model is available.

        Args:
            model: Model name to check

        Returns:
            True if model exists, False otherwise
        """
        try:
            models = self.list_models()
            model_names = [m.name for m in models]
            return model in model_names
        except OllamaError:
            return False

    @staticmethod
    def _parse_frame(data: object, *, raw: bool = False) -> tuple[str, bool, str | None]:
        if not isinstance(data, dict):
            raise OllamaError("Ollama returned an invalid response object.")
        if data.get("error") is not None:
            # Do not echo arbitrary server text, which may contain the input.
            raise OllamaError("Ollama reported a generation error. Check the model/server.")
        message = data.get("message", {})
        done = data.get("done", False)
        reason = data.get("done_reason")
        if (not raw and not isinstance(message, dict)) or not isinstance(done, bool):
            raise OllamaError("Ollama returned an invalid response frame.")
        content = data.get("response", "") if raw else message.get("content", "")
        if not isinstance(content, str) or (reason is not None and not isinstance(reason, str)):
            raise OllamaError("Ollama returned invalid text or completion metadata.")
        return content, done, reason

    def _raise_for_status(
        self,
        response: httpx.Response,
        model: Optional[str] = None,
    ) -> None:
        """Map HTTP status errors to app-level exceptions."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(f"Ollama HTTP error: {status}")
            if status == 404 and model:
                raise OllamaModelError(f"Model '{model}' not found.") from e
            raise OllamaError(f"Ollama API error: {status}") from e

    def _raise_request_error(self, error: httpx.RequestError) -> None:
        """Map transport failures to app-level exceptions."""
        if isinstance(error, httpx.TimeoutException):
            logger.error(f"Ollama request timed out: {error}")
            raise OllamaTimeoutError("Request to Ollama timed out.") from error

        logger.error(f"Ollama connection failed: {error}")
        message = f"Cannot connect to Ollama at {self.host}. Make sure Ollama is running."
        raise OllamaConnectionError(message) from error

    def _new_client(self) -> httpx.Client:
        """Create an HTTP client, allowing tests to inject a mock transport."""
        return httpx.Client(timeout=self._timeout, transport=self._transport, trust_env=False)
