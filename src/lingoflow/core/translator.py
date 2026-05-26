"""
Handles translation service for LingoFlow. 

Wraps the Ollama client with translation-specific logic. 
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from lingoflow.config.settings import AppSettings
from lingoflow.infrastructure.ollama_client import (
    OllamaClient, 
    OllamaConnectionError,
    OllamaError,
    OllamaStreamChunk,
)
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

TRANSLATION_SYSTEM_PROMPT = """You are a professional translator. Your task is to translate text accurately while preserving the original meaning, tone, and style.

Rules:
1. Translate the text naturally, not word-by-word
2. Preserve formatting (line breaks, punctuation) when appropriate
3. Keep proper nouns, brand names, and technical terms as-is when appropriate
4. Output ONLY the translation, no explanations or notes
5. If the source text is already in the target language, return it unchanged"""

TRANSLATION_USER_PROMPT = """Translate the following text from {source_lang} to {target_lang}:

{text}"""

TRANSLATION_USER_PROMPT_AUTO = """Translate the following text to {target_lang}:

{text}"""

# Word Looup feature prompts
WORD_LOOKUP_SYSTEM_PROMPT = """You are a precise dictionary assistant specialized in fuzzy lookups. The user will provide an approximate spelling, a definition, or both.

Your Goal: Identify the word the user is thinking of.

Rules:
1. Provide EXACTLY 3 distinct suggestions, ranked by likelihood.
2. If the input is vague, provide the 3 most common guesses.
3. Format each entry strictly as:
   [Word] ([Part of Speech]): [Brief Definition]
4. Do not include introductory text, conversational fillers, or explanations.
5. Output ONLY the list."""

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
        service = TranslationService()

        # Streaming (for UI)
        for chunk in service.translate_steam("Hello world", "Chinese(Simplified)")
            print(chunk, end="", flush=True)
        
        # Non-streaming 
        result = service.translate("Hello world", "Chinese(Simplified)")
        print(result.translated_text)
    """

    def __init__(self, settings: Optional[AppSettings] = None):
        """
        Initialize the translation service.
        
        Args:
            settings: App settings (loads from disk if not provided)
        """
        self.settings = settings or AppSettings.load()
        self.client = OllamaClient(host=self.settings.ollama.host)
        self._cancelled = False

        logger.info(f"TranslationService initialized with mode: {self.settings.ollama.model}")
    
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
    ) -> Iterator[str]:
        """
        Translate text with streaming output. 

        Args:
            text: Text to translate
            target_language: Target language (uses settins default if None)
            source_language: Source language ("auto" or specific language)
            on_chunk: Optional callback for each chunk (for UI updates in future)
        
        Yields:
            Translation text chunks as they arrive 
        """
        self._cancelled = False

        # Use defaults from settings if not specified
        target_lang = target_language or self.settings.translation.target_language
        source_lang = source_language or self.settings.translation.source_language

        # Build prompt
        system_prompt = self._get_system_prompt()
        user_prompt = self._build_user_prompt(text, source_lang, target_lang)

        logger.info(f"Starting translation: {source_lang} -> {target_lang}")
        logger.debug(f"Source text length: {len(text)} chars")

        def should_cancel() -> bool:
            return self._cancelled or bool(cancel_check and cancel_check())

        try:
            for chunk in self.client.chat_stream(
                message=user_prompt,
                model=self.settings.ollama.model,
                system_prompt=system_prompt,
                cancel_check=should_cancel,
            ):
                if should_cancel():
                    logger.info("Translation cancelled")
                    break

                if chunk.content:
                    if on_chunk:
                        on_chunk(chunk.content)
                    yield chunk.content
        except OllamaConnectionError as e:
            logger.error(f"Ollama connection error during translation: {e}")
            raise
        except OllamaError as e: 
            logger.error(f"Ollama error during translation: {e}")
            raise
    
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
            target_language: Target language (uses settins default if None)
            source_language: Source language ("auto" or specific language)
        
        Returns: 
            TranslationalResult with complete translation
        """
        target_lang = target_language or self.settings.translation.target_language
        source_lang = source_language or self.settings.translation.source_language
        try: 
            # Collect all chunks
            translated_parts = []
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
        except OllamaError as e:
            return TranslationResult(
                source_text=text,
                translated_text="",
                source_language=source_lang,
                target_language=target_lang,
                status=TranslationStatus.ERROR,
                error_message=str(e),
            )
    
    def cancel(self) -> None:
        """Cancel an ongoing streaming translation."""
        self._cancelled = True
        logger.debug("Translation cancellation requested.")
    
    def lookup_word(
        self, 
        attempt: str, 
        meaning: str, 
        language: str = "English"
    ) -> Iterator[str]:
        """
        Help  user find a word they're trying to remember. 

        This is the 'fuzzy word lookup' feature

        Args:
            attempt: What the suer is trying to spell
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

        logger.info(f"Word Lookup using mode: {self.settings.ollama.general_model}")
        if self.settings.privacy.allow_content_logging:
            logger.info(f"Word Lookup: '{attempt}' meaning '{meaning}'")
        else:
            logger.info(
                "Word lookup requested "
                f"(attempt: {len(attempt)} chars, meaning: {len(meaning)} chars, "
                f"language: {language})"
            )

        for chunk in self.client.chat_stream(
            message=user_prompt,
            model=self.settings.ollama.general_model, # for lookup, we use a general model to get better knowledge
            system_prompt=WORD_LOOKUP_SYSTEM_PROMPT,
        ):
            if chunk.content:
                yield chunk.content
    
    # =========================================================
    # Utility Methods
    # =========================================================

    def is_available(self) -> bool:
        """Check if the translation service is avaiable."""
        return self.client.is_available()
    
    def get_available_models(self) -> list[str]:
        """Get list of available Ollama models."""
        try:
            models = self.client.list_models()
            return [m.name for m in models]
        except OllamaError: 
            return []
    
    def update_settings(self, settings: AppSettings) -> None:
        """
        Update service with new settings. 

        Called when suer changes settings in the UI. 
        """
        self.settings = settings
        self.client = OllamaClient(host=settings.ollama.host)
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
