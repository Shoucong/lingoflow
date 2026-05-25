"""
Settings models using Pydantic. 

Provides type-safe configuration with automatic validation, serialization, and default values. 
"""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from lingoflow.config.constants import (
    CONFIG_DIR, 
    CONFIG_FILE,
    DEFAULT_MODEL,
    GENERAL_MODEL,
    LEGACY_CONFIG_FILE,
    DEFAULT_OCR_HOTKEY,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    DEFAULT_TRANSLATE_HOTKEY,
    SUPPORTED_LANGUAGES,
)
from lingoflow.utils.logger import get_logger

# ===========================================================
# Nested Settings Models
# ===========================================================

class OllamaSettings(BaseModel):
    """Ollama connection settings. """
    host: str = Field(
        default=DEFAULT_OLLAMA_HOST, 
        description="Ollama server URL",
    )
    model: str = Field(
        default = DEFAULT_MODEL, 
        description="Default model for translations",
    )
    general_model: str = Field(
        default= GENERAL_MODEL,
        description="Model for general purpose tasks",
    )

class HotkeySettings(BaseModel):
    """Global hotkey settings. """

    translate: str = Field(
        default=DEFAULT_TRANSLATE_HOTKEY, 
        description="Hotkey for triggering translation",
    )
    ocr: str = Field(
        default=DEFAULT_OCR_HOTKEY, 
        description="Hotkey for triggering OCR",
    )

class TranslationSettings(BaseModel):
    """Translation behavior settings."""
    
    source_language: str = Field(
        default = DEFAULT_SOURCE_LANG,
        description="Default source language for translations",
    )
    target_language: str = Field(
        default = DEFAULT_TARGET_LANG,
        description="Default target language for translations",
    )
    # For future: custom prompt templates
    custom_prompt: Optional[str] = Field(
        default=None,
        description="Custom prompt template for translations",
    )

class UISettings(BaseModel):
    """User interface settings."""
    
    theme: str = Field(
        default = "system",
        description="UI theme: 'light', 'dark', or 'system'",
    )
    popup_opacity: float = Field(
        default=0.95,
        ge=0.5,
        le=1.0,
        description="Popup window opacity", 
    )
    font_size: int = Field(
        default=14, 
        ge=10,
        le=24,
        description="Font size in popup",
    )
    show_source_text: bool = Field(
        default=True,
        description="Show original text in popup",
    )
    hide_on_focus_loss: bool = Field(
        default=True,
        description="Hide popup when it loses focus",
    )

class OCRSettings(BaseModel):
    """OCT-Specific settings."""

    language: str = Field(
        default="eng+chi_sim",
        description="OCR language code (e.g., 'eng', 'chi_sim', 'eng+chi_sim')",
    )
    enhance_image: bool = Field(
        default=True, 
        description="Apply image enhancement before OCR",
    )

class OnboardingSettings(BaseModel):
    """First-run onboarding state."""

    completed: bool = Field(
        default=False,
        description="Whether the first-run setup has completed successfully.",
    )

# ===========================================================
# Main Settings Model
# ===========================================================

class AppSettings(BaseModel):
    """
    Main Application settings.

    All settings are grouped into logical sections for clarity. 
    """

    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    hotkeys: HotkeySettings = Field(default_factory=HotkeySettings)
    translation: TranslationSettings = Field(default_factory=TranslationSettings)
    ui: UISettings = Field(default_factory=UISettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    onboarding: OnboardingSettings = Field(default_factory=OnboardingSettings)

    #=========================================================
    # Persistence Methods
    #=========================================================

    @classmethod
    def load(cls) -> "AppSettings":
        """
        Load settings from config file.

        Returns default settings if file doesn't exist or is invalid. 
        """
        config_path = CONFIG_FILE if CONFIG_FILE.exists() else None
        if config_path is None and LEGACY_CONFIG_FILE.exists():
            config_path = LEGACY_CONFIG_FILE

        if config_path:
            try:
                json_content = config_path.read_text(encoding="utf-8")
                settings = cls.model_validate_json(json_content)
            except Exception as e:
                logger = get_logger(__name__)
                logger.warning(
                    f"Could not load settings from {config_path}, using defaults: {e}"
                )
                return cls()

            if config_path == LEGACY_CONFIG_FILE and not CONFIG_FILE.exists():
                try:
                    settings.save()
                    logger = get_logger(__name__)
                    logger.info(
                        f"Migrated settings from {LEGACY_CONFIG_FILE} to {CONFIG_FILE}"
                    )
                except Exception as e:
                    logger = get_logger(__name__)
                    logger.warning(f"Could not migrate settings to {CONFIG_FILE}: {e}")

            return settings
        return cls()
    
    def save(self) -> None:
        """Save current settings to config file."""
        # Ensure config directory exists
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # Write settings as a formatted JSON
        json_content = self.model_dump_json(indent=2)
        CONFIG_FILE.write_text(json_content, encoding="utf-8")

    #=========================================================
    # Utility Methods
    #=========================================================

    @staticmethod
    def get_supported_languages() -> list[str]:
        """Return list of supported languages."""
        return SUPPORTED_LANGUAGES
    
    def reset_to_defaults(self) -> "AppSettings":
        """Reset all settings to defaults and save."""
        default_settings = AppSettings()
        default_settings.save()
        return default_settings
