"""
Ollama API client with streaming support. 

Handles all communication with the local Ollama server.
"""

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Optional

import httpx
from lingoflow.config.constants import (
    OLLAMA_CHAT_ENDPOINT, 
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_READ_TIMEOUT, 
    OLLAMA_TAGS_ENDPOINT
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
    """Represents an avaiable Ollama model."""

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

class OllamaModelERROR(OllamaError):
    """Model-realted error (not found, failed to load, etc)."""

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

    def __init__(self, host: str = "http://localhost:11434"):
        """
        Initialize the Ollama client. 

        Args: 
            host: Ollama server URL 
        """
        self.host = host.rstrip("/")
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
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
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
                        
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse chunk: {line[:100]}...")
                            continue
        except httpx.ConnectError as e:
            logger.error("Connection failed: {e}")
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.host}"
                "Make sure Ollama is running."
            ) from e
        except httpx.TimeoutException as e: 
            logger.error(f"Request timed out: {e}")
            raise OllamaTimeoutError("Request to Ollama timed out.") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code}")
            if e.response.status_code == 404:
                raise OllamaModelERROR(f"Model '{model}' not found.") from e
            raise OllamaError(f"Ollama API error: {e.response.status_code}") from e

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
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                return OllamaResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=data.get("model", model),
                    done=True,
                    total_duration=data.get("total_duration"),
                    eval_count=data.get("eval_count"),
                )
            
        except httpx.ConnectError as e:
            logger.error(f"Connection failed: {e}")
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.host}"
                "Make sure Ollama is running."
            ) from e
        except httpx.TimeoutException as e: 
            logger.error(f"Request timed out: {e}")
            raise OllamaTimeoutError("Request to Ollama timed out.") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code}")
            raise OllamaError(f"Ollama API error: {e.response.status_code}") from e

    def list_models(self) -> list[OllamaModel]:
        """
        Get list of avaiable models from Ollama. 
        
        Returns:
            List of OllamaModel objects
        Raise:
            OllamaConnectionError: if cannot connect to server
        """
        url = f"{self.host}{OLLAMA_TAGS_ENDPOINT}"

        logger.debug("Fetching avaiable models")

        try: 
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()

                models = [
                    OllamaModel(
                        name=m.get("name", ""),
                        size=m.get("size", 0),
                        modified_at=m.get("modified_at", ""),
                    )
                    for m in data.get("models", [])
                ]

                logger.info(f"Found {len(models)} avaiable models")
                return models
        except httpx.ConnectError as e:
            logger.error(f"Connection failed: {e}")
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.host}."
                "Make sure Ollama is running"
            ) from e

    def is_available(self) -> bool:
        """
        Check if Ollama server is reachable. 

        Returns:
            True if server responds, False otherwise
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def check_model_exists(self, model: str) -> bool:
        """
        Check if a specific model is avaiable . 
        
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