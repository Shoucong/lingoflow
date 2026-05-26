"""
Settings models using Pydantic.

Provides type-safe configuration with automatic validation, serialization, and default values.
"""

from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lingoflow.config.constants import (
    CONFIG_BACKUP_FILE,
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_MODEL,
    DEFAULT_OCR_HOTKEY,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    DEFAULT_TRANSLATE_HOTKEY,
    GENERAL_MODEL,
    LEGACY_CONFIG_FILE,
    SUPPORTED_LANGUAGES,
    SUPPORTED_OCR_LANGUAGES,
)
from lingoflow.utils.logger import get_logger

# ===========================================================
# Nested Settings Models
# ===========================================================

HOTKEY_MODIFIERS = {"alt", "option", "cmd", "command", "ctrl", "control", "shift"}
HOTKEY_KEYS = {
    "a",
    "s",
    "d",
    "f",
    "h",
    "g",
    "z",
    "x",
    "c",
    "v",
    "b",
    "q",
    "w",
    "e",
    "r",
    "y",
    "t",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "0",
    "=",
    "-",
    "]",
    "o",
    "u",
    "[",
    "i",
    "p",
    "l",
    "j",
    "'",
    "k",
    ";",
    "\\",
    ",",
    "/",
    "n",
    "m",
    ".",
    "`",
    "space",
    "tab",
    "return",
    "enter",
    "escape",
    "esc",
}


class SettingsModel(BaseModel):
    """Base model for persisted settings."""

    model_config = ConfigDict(validate_assignment=True, extra="ignore")


def _normalize_hotkey(value: str) -> str:
    """Validate and normalize a '<alt>+d' style hotkey."""
    hotkey = value.strip().lower()
    tokens = [token.strip().removeprefix("<").removesuffix(">") for token in hotkey.split("+")]
    tokens = [token for token in tokens if token]

    if not tokens:
        raise ValueError("hotkey cannot be empty")

    modifier_count = sum(token in HOTKEY_MODIFIERS for token in tokens)
    key_tokens = [token for token in tokens if token not in HOTKEY_MODIFIERS]

    if modifier_count == 0:
        raise ValueError("hotkey must include at least one modifier")
    if len(key_tokens) != 1:
        raise ValueError("hotkey must include exactly one non-modifier key")
    if key_tokens[0] not in HOTKEY_KEYS:
        raise ValueError(f"unsupported hotkey key '{key_tokens[0]}'")

    return value.strip()


class OllamaSettings(SettingsModel):
    """Ollama connection settings."""

    host: str = Field(
        default=DEFAULT_OLLAMA_HOST,
        description="Ollama server URL",
    )
    model: str = Field(
        default=DEFAULT_MODEL,
        description="Default model for translations",
    )
    general_model: str = Field(
        default=GENERAL_MODEL,
        description="Model for general purpose tasks",
    )

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Validate Ollama host URL."""
        host = value.strip().rstrip("/")
        parsed = urlparse(host)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "Ollama host must be an http(s) URL, for example http://localhost:11434"
            )
        return host

    @field_validator("model", "general_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        """Validate model names are not blank."""
        model = value.strip()
        if not model:
            raise ValueError("model name cannot be empty")
        return model


class HotkeySettings(SettingsModel):
    """Global hotkey settings."""

    translate: str = Field(
        default=DEFAULT_TRANSLATE_HOTKEY,
        description="Hotkey for triggering translation",
    )
    ocr: str = Field(
        default=DEFAULT_OCR_HOTKEY,
        description="Hotkey for triggering OCR",
    )

    @field_validator("translate", "ocr")
    @classmethod
    def validate_hotkey(cls, value: str) -> str:
        """Validate hotkey syntax."""
        return _normalize_hotkey(value)

    @model_validator(mode="after")
    def validate_distinct_hotkeys(self) -> "HotkeySettings":
        """Require separate shortcuts for translation and OCR."""
        if self.translate.strip().lower() == self.ocr.strip().lower():
            raise ValueError("Translate and OCR hotkeys must be different")
        return self


class TranslationSettings(SettingsModel):
    """Translation behavior settings."""

    source_language: str = Field(
        default=DEFAULT_SOURCE_LANG,
        description="Default source language for translations",
    )
    target_language: str = Field(
        default=DEFAULT_TARGET_LANG,
        description="Default target language for translations",
    )
    # For future: custom prompt templates
    custom_prompt: Optional[str] = Field(
        default=None,
        description="Custom prompt template for translations",
    )

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, value: str) -> str:
        """Validate source language."""
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported source language '{value}'")
        return value

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str) -> str:
        """Validate target language."""
        if value == "auto" or value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported target language '{value}'")
        return value


class UISettings(SettingsModel):
    """User interface settings."""

    theme: str = Field(
        default="system",
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

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        """Validate UI theme."""
        theme = value.strip().lower()
        if theme not in {"system", "light", "dark"}:
            raise ValueError("theme must be system, light, or dark")
        return theme


class OCRSettings(SettingsModel):
    """OCR-specific settings."""

    language: str = Field(
        default="eng+chi_sim",
        description="OCR language code (e.g., 'eng', 'chi_sim', 'eng+chi_sim')",
    )
    enhance_image: bool = Field(
        default=True,
        description="Apply image enhancement before OCR",
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Validate OCR language."""
        if value not in SUPPORTED_OCR_LANGUAGES:
            raise ValueError(f"unsupported OCR language '{value}'")
        return value


class OnboardingSettings(SettingsModel):
    """First-run onboarding state."""

    completed: bool = Field(
        default=False,
        description="Whether the first-run setup has completed successfully.",
    )


class PrivacySettings(SettingsModel):
    """Privacy and troubleshooting settings."""

    allow_content_logging: bool = Field(
        default=False,
        description="Include selected text, OCR text, and generated content in logs.",
    )
    keep_ocr_captures: bool = Field(
        default=False,
        description="Keep OCR screenshot files after recognition for troubleshooting.",
    )


# ===========================================================
# Main Settings Model
# ===========================================================


class AppSettings(SettingsModel):
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
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)

    # =========================================================
    # Persistence Methods
    # =========================================================

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
                settings = cls._load_file(config_path)
            except Exception as e:
                logger = get_logger(__name__)
                logger.warning(f"Could not load settings from {config_path}, using defaults: {e}")
                backup_settings = cls._load_backup_after_failure()
                if backup_settings:
                    return backup_settings
                return cls()

            if config_path == LEGACY_CONFIG_FILE and not CONFIG_FILE.exists():
                try:
                    settings.save()
                    logger = get_logger(__name__)
                    logger.info(f"Migrated settings from {LEGACY_CONFIG_FILE} to {CONFIG_FILE}")
                except Exception as e:
                    logger = get_logger(__name__)
                    logger.warning(f"Could not migrate settings to {CONFIG_FILE}: {e}")

            return settings
        return cls()

    def save(self) -> None:
        """Save current settings to config file atomically."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        json_content = self.model_dump_json(indent=2)
        temp_file = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.tmp")
        temp_file.write_text(json_content, encoding="utf-8")

        if CONFIG_FILE.exists():
            try:
                CONFIG_BACKUP_FILE.write_text(
                    CONFIG_FILE.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            except OSError as e:
                logger = get_logger(__name__)
                logger.warning(f"Could not write settings backup: {e}")

        temp_file.replace(CONFIG_FILE)

    # =========================================================
    # Utility Methods
    # =========================================================

    @staticmethod
    def get_supported_languages() -> list[str]:
        """Return list of supported languages."""
        return SUPPORTED_LANGUAGES

    def reset_to_defaults(self) -> "AppSettings":
        """Reset all settings to defaults and save."""
        default_settings = AppSettings()
        default_settings.save()
        return default_settings

    @classmethod
    def _load_file(cls, path) -> "AppSettings":
        """Load and validate settings from a JSON file."""
        json_content = path.read_text(encoding="utf-8")
        return cls.model_validate_json(json_content)

    @classmethod
    def _load_backup_after_failure(cls) -> Optional["AppSettings"]:
        """Return backup settings if available and valid."""
        if not CONFIG_BACKUP_FILE.exists():
            return None

        try:
            settings = cls._load_file(CONFIG_BACKUP_FILE)
            logger = get_logger(__name__)
            logger.warning(f"Recovered settings from backup: {CONFIG_BACKUP_FILE}")
            return settings
        except Exception as e:
            logger = get_logger(__name__)
            logger.warning(f"Could not load settings backup: {e}")
            return None
