"""Compose the local translation service with native language identification."""

from lingoflow.config.settings import AppSettings
from lingoflow.core.translator import TranslationService
from lingoflow.infrastructure.macos.language import detect_source_language
from lingoflow.infrastructure.ollama_client import create_ollama_client


def create_translation_service(settings: AppSettings | None = None) -> TranslationService:
    return TranslationService(
        settings,
        client_factory=create_ollama_client,
        language_detector=detect_source_language,
    )
