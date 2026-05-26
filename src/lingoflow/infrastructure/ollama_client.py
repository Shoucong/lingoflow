"""
Ollama API client with streaming support.

Handles all communication with the local Ollama server.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Optional

import httpx

from lingoflow.config.constants import (
    OLLAMA_CHAT_ENDPOINT,
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_READ_TIMEOUT,
    OLLAMA_TAGS_ENDPOINT,
)
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

# ===========================================================
# Data Classes
# ===========================================================

@dataclass
class OllamaResponse:
    """Represents a complete (non-streaming) response from Ollama"""

    content: str
    model: str
    done: bool
    total_duration: Optional[int] = None
    eval_count: Optional[int] = None

@dataclass
class OllamaStreamChunk:
    """Represents a single chunk from a streaming response. """

    content: str
    done: bool

@dataclass
class OllamaModel:
    """Represents an available Ollama model."""

    name: str
    size: int
    modified_at: str

# ===========================================================
# Exceptions
# ===========================================================

class OllamaError(Exception):
    """Base exception for Ollama-related errors."""

    pass

class OllamaConnectionError(OllamaError):
    """Failed to connect to Ollama server."""

    pass

class OllamaModelError(OllamaError):
    """Model-related error (not found, failed to load, etc)."""

    pass

class OllamaTimeoutError(OllamaError):
    """Request Timed out."""

    pass

# ===========================================================
# Ollama Client
# ===========================================================

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
    ):
        """
        Initialize the Ollama client.

        Args:
            host: Ollama server URL
            transport: Optional httpx transport for tests.
        """
        self.host = host.rstrip("/")
        self._transport = transport
        self._timeout = httpx.Timeout(
            connect=OLLAMA_CONNECT_TIMEOUT,
            read=OLLAMA_READ_TIMEOUT,
            write=10.0,
            pool=5.0,
        )
        logger.debug(f"OllamaClient initialized with host; {self.host}")

    # ===========================================================
    # Public Methods
    # ===========================================================

    def chat_stream(
        self,
        message: str,
        model: str,
        system_prompt: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Iterator[OllamaStreamChunk]:
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
        url = f"{self.host}{OLLAMA_CHAT_ENDPOINT}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        logger.debug(f"Starting streaming chat with model: {model}")
        logger.debug(f"Message length: {len(message)} chars")

        try:
            with self._new_client() as client:
                with client.stream("POST", url, json=payload) as response:
                    self._raise_for_status(response, model=model)

                    for line in response.iter_lines():
                        if cancel_check and cancel_check():
                            logger.info("Streaming chat cancelled")
                            break

                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            done = data.get("done", False)

                            if content or done:
                                yield OllamaStreamChunk(content=content, done=done)

                            if done:
                                logger.debug("Streaming complete.")

                        except json.JSONDecodeError:
                            logger.error(
                                f"Failed to parse stream chunk ({len(line)} chars)"
                            )
                            continue
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

                return OllamaResponse(
                    content=data.get("message", {}).get("content", ""),
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
                response = client.get(url)
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
                response = client.get(f"{self.host}/api/tags")
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
        raise OllamaConnectionError(
            f"Cannot connect to Ollama at {self.host}. "
            "Make sure Ollama is running."
        ) from error

    def _new_client(self) -> httpx.Client:
        """Create an HTTP client, allowing tests to inject a mock transport."""
        return httpx.Client(timeout=self._timeout, transport=self._transport)
