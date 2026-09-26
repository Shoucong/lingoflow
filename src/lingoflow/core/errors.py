"""Failure categories shared by workflows and native/model adapters."""


class TranslationError(Exception):
    """A translation failed; any partial text is incomplete."""


class TranslationCancelledError(TranslationError):
    """The request owner stopped generation."""


class ProviderConnectionError(TranslationError):
    """The model provider could not be reached."""


class ProviderModelError(TranslationError):
    """The requested model is unavailable or incompatible."""


class ProviderTimeoutError(TranslationError):
    """The model provider timed out."""


class OCRError(Exception):
    """A capture or recognition operation failed."""


class ScreenCaptureError(OCRError):
    """Screen acquisition failed."""


class VisionError(OCRError):
    """Native text recognition failed."""
