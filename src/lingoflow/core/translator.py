"""
Handles translation service for LingoFlow.

Wraps the Ollama client with translation-specific logic.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from lingoflow.config.settings import AppSettings
from lingoflow.core.errors import (
    ProviderConnectionError,
    TranslationCancelledError,
    TranslationError,
)
from lingoflow.core.ports import ChatProvider
from lingoflow.core.text_preparation import TranslationCheckpoint, fingerprint, split_text
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

# ==========================================================
# Data Types
# ==========================================================


class TranslationStatus(Enum):
    """Status of a translation operation."""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class TranslationResult:
    """Complete result of a translation."""

    source_text: str
    translated_text: str
    source_language: str
    target_language: str
    status: TranslationStatus
    error_message: Optional[str] = None


# ==========================================================
# Prompt Templates
# ==========================================================

TRANSLATION_SYSTEM_PROMPT = (
    "You are a professional translator. Your task is to translate text accurately "
    "while preserving the original meaning, tone, and style.\n\n"
    "Rules:\n"
    "1. Translate the text naturally, not word-by-word\n"
    "2. Preserve formatting (line breaks, punctuation) when appropriate\n"
    "3. Keep proper nouns, brand names, and technical terms as-is when appropriate\n"
    "4. Output ONLY the translation, no explanations or notes\n"
    "5. If the source text is already in the target language, return it unchanged"
)

TRANSLATION_USER_PROMPT = """Translate the following text from {source_lang} to {target_lang}:

{text}"""

TRANSLATION_USER_PROMPT_AUTO = """Translate the following text to {target_lang}:

{text}"""

# Word lookup feature prompts
WORD_LOOKUP_SYSTEM_PROMPT = (
    "You are a precise dictionary assistant specialized in fuzzy lookups. The user "
    "will provide an approximate spelling, a definition, or both.\n\n"
    "Your Goal: Identify the word the user is thinking of.\n\n"
    "Rules:\n"
    "1. Provide EXACTLY 3 distinct suggestions, ranked by likelihood.\n"
    "2. If the input is vague, provide the 3 most common guesses.\n"
    "3. Format each entry strictly as:\n"
    "   [Word] ([Part of Speech]): [Brief Definition]\n"
    "4. Do not include introductory text, conversational fillers, or explanations.\n"
    "5. Output ONLY the list."
)

WORD_LOOKUP_USER_PROMPT = """Find the word based on these clues:
- Approximate Spelling: {attempt}
- Intended Meaning: {meaning}
- Target Language: {language}

Output the list now:"""

# ==========================================================
# Translation Service
# ==========================================================


class TranslationService:
    """
    Handles prompt construction, language options, and provides both
    streaming and non-streaming translation methods.

    Examples:
        service = TranslationService(settings, client=provider)

        # Streaming (for UI)
        for chunk in service.translate_stream("Hello world", "Chinese(Simplified)")
            print(chunk, end="", flush=True)

        # Non-streaming
        result = service.translate("Hello world", "Chinese(Simplified)")
        print(result.translated_text)
    """

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        *,
        client: ChatProvider | None = None,
        client_factory: Callable[[AppSettings], ChatProvider] | None = None,
    ):
        """
        Initialize the translation service.

        Args:
            settings: App settings (loads from disk if not provided)
        """
        self.settings = settings or AppSettings.load()
        if client is None and client_factory is None:
            raise TypeError("TranslationService requires a client or client_factory")
        self._client_factory = client_factory
        self.client = client if client is not None else client_factory(self.settings)

        logger.info(f"TranslationService initialized with model: {self.settings.ollama.model}")

    # =========================================================
    # Public Methods
    # =========================================================

    def translate_stream(
        self,
        text: str,
        target_language: Optional[str] = None,
        source_language: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        checkpoint: TranslationCheckpoint | None = None,
        on_checkpoint: Callable[[TranslationCheckpoint], None] | None = None,
    ) -> Iterator[str]:
        """Translate complete source segments, retaining only completed retry checkpoints."""
        if cancel_check and cancel_check():
            return
        if not text.strip():
            raise TranslationError("Enter text to translate.")
        settings = self.settings.model_copy(deep=True)
        client = self.client
        target = target_language or settings.translation.target_language
        source = source_language or settings.translation.source_language
        system = settings.translation.custom_prompt or TRANSLATION_SYSTEM_PROMPT
        if settings.translation.preset == "academic":
            system += (
                "\nPreserve citations, equations, symbols, numerical values, units and "
                "technical abbreviations. Do not add explanations or invent references."
            )
        prefix = self._build_user_prompt("", source, target)
        # Reserve output plus actual prompt bytes, a bounded context hint, and role tokens.
        overhead = len((system + prefix).encode("utf-8")) + 512
        budget = min(
            settings.ollama.context_window - settings.ollama.max_output_tokens - overhead,
            settings.ollama.max_output_tokens * 2,
        )
        if budget < 128:
            raise TranslationError(
                "Prompt and output budget leave too little input space. Increase context."
            )
        try:
            segments = split_text(text, budget)
        except ValueError as error:
            raise TranslationError(str(error)) from error
        key = fingerprint(
            text,
            {
                "ollama": settings.ollama.model_dump(),
                "system": system,
                "source": source,
                "target": target,
            },
        )
        completed = (
            list(checkpoint.completed) if checkpoint and checkpoint.fingerprint == key else []
        )
        if len(completed) > len(segments):
            completed = []
        if on_checkpoint:
            on_checkpoint(TranslationCheckpoint(key, tuple(completed), len(segments)))
        for result in completed:
            if cancel_check and cancel_check():
                return
            if on_chunk:
                on_chunk(result)
            yield result
        options = {
            "num_ctx": settings.ollama.context_window,
            "num_predict": settings.ollama.max_output_tokens,
            "temperature": settings.ollama.temperature,
        }
        think = {"auto": None, "off": False, "on": True}[settings.ollama.thinking]
        for index in range(len(completed), len(segments)):
            if cancel_check and cancel_check():
                return
            segment = segments[index]
            translated = []
            pending_space = ""
            if segment.text.strip():
                prompt = self._build_user_prompt(segment.text, source, target)
                if index:
                    context = (
                        segments[index - 1]
                        .text.encode("utf-8")[-256:]
                        .decode(
                            "utf-8",
                            errors="ignore",
                        )
                    )
                    prompt = (
                        "Previous source context (do not translate again):\n"
                        + context
                        + "\nTranslate only the current segment below.\n"
                        + prompt
                    )
                try:
                    for chunk in client.chat_stream(
                        message=prompt,
                        model=settings.ollama.model,
                        system_prompt=system,
                        cancel_check=cancel_check,
                        options=options,
                        keep_alive=settings.ollama.keep_alive,
                        think=think,
                    ):
                        if cancel_check and cancel_check():
                            return
                        combined = pending_space + chunk.content
                        visible = combined.rstrip()
                        pending_space = combined[len(visible) :]
                        if visible:
                            translated.append(visible)
                            if on_chunk:
                                on_chunk(visible)
                            yield visible
                except TranslationCancelledError:
                    raise
                except TranslationError as error:
                    error_type = (
                        ProviderConnectionError
                        if isinstance(error, ProviderConnectionError)
                        else TranslationError
                    )
                    raise error_type(f"Part {index + 1}/{len(segments)}: {error}") from error
                if cancel_check and cancel_check():
                    return
                if not any(part.strip() for part in translated):
                    raise TranslationError(
                        f"Part {index + 1}/{len(segments)}: The model returned no translation."
                    )
            if segment.separator:
                if on_chunk:
                    on_chunk(segment.separator)
                yield segment.separator
            completed.append("".join(translated) + segment.separator)
            if on_checkpoint:
                on_checkpoint(TranslationCheckpoint(key, tuple(completed), len(segments)))

    def translate(
        self,
        text: str,
        target_language: Optional[str] = None,
        source_language: Optional[str] = None,
    ) -> TranslationResult:
        """
        Translate text and return complete result.

        For UI use.

        Args:
            text: Text to translate
            target_language: Target language (uses settings default if None)
            source_language: Source language ("auto" or specific language)

        Returns:
            TranslationResult with complete translation
        """
        target_lang = target_language or self.settings.translation.target_language
        source_lang = source_language or self.settings.translation.source_language
        translated_parts = []
        try:
            # Collect all chunks
            for chunk in self.translate_stream(text, target_lang, source_lang):
                translated_parts.append(chunk)

            translated_text = "".join(translated_parts)

            return TranslationResult(
                source_text=text,
                translated_text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
                status=TranslationStatus.COMPLETED,
            )
        except TranslationCancelledError:
            return TranslationResult(
                text,
                "".join(translated_parts),
                source_lang,
                target_lang,
                TranslationStatus.CANCELLED,
            )
        except TranslationError as e:
            return TranslationResult(
                source_text=text,
                translated_text="".join(translated_parts),
                source_language=source_lang,
                target_language=target_lang,
                status=TranslationStatus.ERROR,
                error_message=str(e),
            )

    def cancel(self) -> None:
        """Cancel an ongoing streaming translation."""
        self.client.cancel()
        logger.debug("Translation cancellation requested.")

    def lookup_word(self, attempt: str, meaning: str, language: str = "English") -> Iterator[str]:
        """
        Help the user find a word they're trying to remember.

        This is the 'fuzzy word lookup' feature

        Args:
            attempt: What the user is trying to spell
            meaning: Description of what the word means
            language: Language of the word

        Yields:
            Response chunks with word suggestions
        """
        user_prompt = WORD_LOOKUP_USER_PROMPT.format(
            attempt=attempt,
            meaning=meaning,
            language=language,
        )

        logger.info(f"Word lookup using model: {self.settings.ollama.general_model}")
        if self.settings.privacy.allow_content_logging:
            logger.info(f"Word lookup: '{attempt}' meaning '{meaning}'")
        else:
            logger.info(
                "Word lookup requested "
                f"(attempt: {len(attempt)} chars, meaning: {len(meaning)} chars, "
                f"language: {language})"
            )

        # For lookup, use the general model to get broader vocabulary knowledge.
        for chunk in self.client.chat_stream(
            message=user_prompt,
            model=self.settings.ollama.general_model,
            system_prompt=WORD_LOOKUP_SYSTEM_PROMPT,
        ):
            if chunk.content:
                yield chunk.content

    # =========================================================
    # Utility Methods
    # =========================================================

    def is_available(self) -> bool:
        """Check if the translation service is available."""
        return self.client.is_available()

    def get_available_models(self) -> list[str]:
        """Get list of available Ollama models."""
        try:
            models = self.client.list_models()
            return [m.name for m in models]
        except TranslationError:
            return []

    def update_settings(self, settings: AppSettings) -> None:
        """
        Update service with new settings.

        Called when the user changes settings in the UI.
        """
        self.cancel()
        self.settings = settings
        if self._client_factory is not None:
            self.client = self._client_factory(settings)
        logger.info(f"Settings updated, model: {settings.ollama.model}")

    # =========================================================
    # Private Methods
    # =========================================================

    def _get_system_prompt(self) -> str:
        """Get the system prompt, using custom if set."""
        if self.settings.translation.custom_prompt:
            return self.settings.translation.custom_prompt
        return TRANSLATION_SYSTEM_PROMPT

    def _build_user_prompt(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Build the user prompt for translation."""
        if source_lang.lower() == "auto":
            return TRANSLATION_USER_PROMPT_AUTO.format(
                target_lang=target_lang,
                text=text,
            )
        else:
            return TRANSLATION_USER_PROMPT.format(
                source_lang=source_lang,
                target_lang=target_lang,
                text=text,
            )
