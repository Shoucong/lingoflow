"""
OCR service for LingoFlow.

Handles screen capture and text extraction.
Uses Apple Vision and macOS screencapture.
"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import objc
from PIL import Image, ImageEnhance, ImageFilter

from lingoflow.config.constants import OCR_CAPTURE_DIR
from lingoflow.config.settings import AppSettings
from lingoflow.core.errors import ScreenCaptureError
from lingoflow.core.models import CaptureRegion, OCRResult
from lingoflow.infrastructure.macos.screen_capture import ScreenCaptureRunner
from lingoflow.infrastructure.macos.vision import VISION_AVAILABLE, VisionRecognizer
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class OCRService:
    """
    macOS screen capture and OCR text extraction service.

    Example:
        ocr = OCRService()

        # Capture and extract in one step
        result = ocr.capture_and_extract(region)
        print(result.text)

        # Or extract from existing image
        result = ocr.extract_text(Path("/path/to/image.png"))
    """

    # Language mapping from app settings codes to Apple Vision identifiers.
    # Order matters: Vision uses the first language's model. Its Chinese/Japanese
    # models also read Latin letters, but the English model cannot read CJK text, so
    # "en-US" first returned nothing for Chinese and garbled mixed lines. CJK comes
    # first in mixed options (measured: Chinese 98-100%, mixed 90-95% character accuracy).
    LANGUAGE_MAP = {
        "eng": ["en-US"],
        "chi_sim": ["zh-Hans"],
        "chi_tra": ["zh-Hant"],
        "jpn": ["ja-JP"],
        "kor": ["ko-KR"],
        "fra": ["fr-FR"],
        "deu": ["de-DE"],
        "spa": ["es-ES"],
        "por": ["pt-BR"],
        "ita": ["it-IT"],
        "rus": ["ru-RU"],
        # Composite options for mixed-language documents
        "eng+chi_sim": ["zh-Hans", "en-US"],
        "eng+jpn": ["ja-JP", "en-US"],
    }

    def __init__(self, settings: Optional[AppSettings] = None):
        """
        Initialize the OCR service

        Args:
            settings: App settings (loads from disk if not provided)
        """
        self.settings = settings or AppSettings.load()
        self._capture_dir = OCR_CAPTURE_DIR
        self._vision_gate = threading.Lock()
        self.capture = ScreenCaptureRunner()
        self.recognizer = VisionRecognizer()
        self._prepare_capture_dir()
        if not self.settings.privacy.keep_ocr_captures:
            self.cleanup_stale_captures()

        # Verify OCR backend availability
        self._verify_ocr_backend()

        logger.info("OCRService initialized " f"(language: {self.settings.ocr.language})")

    # ==========================================================
    # Public Methods
    # ==========================================================

    def extract_text(
        self,
        image_path: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> OCRResult:
        """
        Extract text from an image file.

        Uses Apple Vision.

        Args:
            image_path: Path to the image file

        Returns:
            OCRResult with extracted text
        """
        logger.debug("Extracting text from image")

        if not image_path.exists():
            return OCRResult(
                text="",
                success=False,
                error_message=f"Image file not found: {image_path}",
            )

        prepared = None
        try:
            with self._vision_gate, objc.autorelease_pool():
                if cancel_check and cancel_check():
                    return OCRResult(text="", cancelled=True)
                recognition_path = image_path
                if self.settings.ocr.enhance_image:
                    prepared = self._new_capture_path()
                    with Image.open(image_path) as image:
                        self._preprocess_image(image).save(prepared, format="PNG")
                    self._secure_capture_file(prepared)
                    recognition_path = prepared
                if cancel_check and cancel_check():
                    return OCRResult(text="", cancelled=True)
                result = self._extract_text_apple_vision(recognition_path, cancel_check)
                result.source_image_path = str(image_path)
                return result
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return OCRResult(text="", success=False, error_message=str(e))
        finally:
            if prepared is not None:
                prepared.unlink(missing_ok=True)

    def capture_screen_region(self, region: CaptureRegion) -> Path:
        """
        Capture a region of the screen.

        Args:
            region: Screen region to capture

        Returns:
            Path to the captured image file

        Raises:
            ScreenCaptureError: if capture fails
        """
        output_path = self._new_capture_path()

        logger.debug(f"Capturing region: {region}")

        try:
            self._capture_macos(region, output_path)

            if not output_path.exists():
                raise ScreenCaptureError("Screenshot file was not created")

            self._secure_capture_file(output_path)

            logger.info("Screen captured to managed OCR cache")
            return output_path

        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            raise ScreenCaptureError(f"Failed to capture screen: {e}") from e

    def capture_interactive(
        self,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Optional[Path]:
        """
        Let user interactively select a screen region to capture.

        Returns:
            Path to captured image, or None if canceled
        """
        output_path = self._new_capture_path()
        logger.info("Starting interactive screen capture")

        try:
            return self._capture_interactive_macos(output_path, cancel_check)
        except ScreenCaptureError:
            self.cleanup_capture(output_path)
            raise
        except Exception as e:
            logger.error(f"Interactive capture failed: {e}")
            self.cleanup_capture(output_path)
            return None

    def capture_and_extract(self, region: Optional[CaptureRegion] = None) -> OCRResult:
        """
        Capture screen region and extract text in one step.

        Args:
            region: Specific region to capture (interactive if None)

        Returns:
            OCRResult with extracted text
        """
        try:
            if region:
                image_path = self.capture_screen_region(region)
            else:
                image_path = self.capture_interactive()
                if image_path is None:
                    return OCRResult(
                        text="",
                        success=False,
                        error_message="Screen capture cancelled",
                    )

            result = self.extract_text(image_path)
            if self.cleanup_capture(image_path):
                result.source_image_path = None
            return result

        except ScreenCaptureError as e:
            return OCRResult(text="", success=False, error_message=str(e))

    def get_available_languages(self) -> List[str]:
        """
        Get list of available OCR languages.

        Returns:
            List of language codes
        """
        return list(self.LANGUAGE_MAP.keys())

    def update_settings(self, settings: AppSettings) -> None:
        """Update service with new settings"""
        self.settings = settings
        if not self.settings.privacy.keep_ocr_captures:
            self.cleanup_stale_captures()
        logger.info(f"OCR settings updated, language: {settings.ocr.language}")

    def cleanup_capture(self, image_path: Path | str) -> bool:
        """Delete a managed OCR capture unless troubleshooting retention is enabled."""
        if self.settings.privacy.keep_ocr_captures:
            logger.debug("Keeping OCR capture for troubleshooting")
            return False

        path = Path(image_path)
        if not self._is_managed_capture_path(path):
            logger.debug("Refusing to delete unmanaged OCR path")
            return False

        try:
            if path.exists():
                path.unlink()
                logger.debug("Deleted OCR capture")
                return True
        except OSError as e:
            logger.warning(f"Could not delete OCR capture {path}: {e}")
        return False

    def cleanup_stale_captures(self) -> None:
        """Remove old managed captures when capture retention is disabled."""
        for capture_path in self._capture_dir.glob("capture-*.png"):
            self.cleanup_capture(capture_path)

    # ==========================================================
    # macOS implementation
    # ==========================================================

    def _extract_text_apple_vision(self, image_path: Path, cancel_check=None) -> OCRResult:
        return self.recognizer.recognize(image_path, self._get_apple_languages(), cancel_check)

    def _get_apple_languages(self) -> List[str]:
        """
        Get Apple Vision language identifiers from settings.

        Falls back to English + Chinese if language not mapped.
        """
        lang = self.settings.ocr.language

        if lang in self.LANGUAGE_MAP:
            return self.LANGUAGE_MAP[lang]

        # default
        logger.warning(f"Unknown languages '{lang}', defaulting to zh-Hans + en-US")
        return ["zh-Hans", "en-US"]

    # ==========================================================
    # macOS: Screen Capture
    # ==========================================================

    def cancel(self) -> None:
        """Cancel only the native operations owned by this service."""
        self.capture.cancel()
        self.recognizer.cancel()

    def _capture_macos(self, region: CaptureRegion, output_path: Path) -> None:
        result = self.capture.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-R",
                f"{region.x},{region.y},{region.width},{region.height}",
                str(output_path),
            ],
            10.0,
        )
        if result.returncode != 0:
            raise ScreenCaptureError(self._format_macos_capture_error(result.stderr))

    def _capture_interactive_macos(self, output_path: Path, cancel_check=None) -> Optional[Path]:
        result = self.capture.run(
            ["/usr/sbin/screencapture", "-i", "-s", "-x", str(output_path)],
            120.0,
            cancel_check,
        )
        if result.returncode == -1:
            self.cleanup_capture(output_path)
            return None
        if output_path.exists():
            self._secure_capture_file(output_path)
            return output_path
        if result.returncode != 0 and result.stderr.strip():
            raise ScreenCaptureError(self._format_macos_capture_error(result.stderr))
        return None

    # ==========================================================
    # Utility Methods
    # ==========================================================

    def _verify_ocr_backend(self) -> None:
        """Verify Apple Vision is available."""
        if VISION_AVAILABLE:
            logger.debug("Apple Vision framework available")
        else:
            logger.warning(
                "Apple Vision not available. " "Install PyObjC: pip install pyobjc-framework-Vision"
            )

    def _format_macos_capture_error(self, stderr: str) -> str:
        """Return a user-facing macOS screen capture error."""
        detail = stderr.strip() if stderr else "Unknown screencapture error"
        lower_detail = detail.lower()

        if "not authorized" in lower_detail or "permission" in lower_detail:
            return (
                "Screen capture is not authorized. "
                "Grant Screen Recording permission to LingoFlow, then restart the app."
            )

        return f"Screen capture failed: {detail}"

    def _prepare_capture_dir(self) -> None:
        """Create a private app cache folder for OCR screenshots."""
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._capture_dir.chmod(0o700)
        except OSError as e:
            logger.warning(f"Could not set OCR capture directory permissions: {e}")

    def _new_capture_path(self) -> Path:
        """Return a unique managed OCR capture path."""
        return self._capture_dir / f"capture-{uuid4().hex}.png"

    def _secure_capture_file(self, image_path: Path) -> None:
        """Restrict capture file permissions where the filesystem supports it."""
        try:
            image_path.chmod(0o600)
        except OSError as e:
            logger.warning(f"Could not set OCR capture file permissions: {e}")

    def _is_managed_capture_path(self, image_path: Path) -> bool:
        """Return whether a path belongs to the managed OCR capture directory."""
        try:
            return (
                image_path.resolve().is_relative_to(self._capture_dir.resolve())
                and image_path.name.startswith("capture-")
                and image_path.suffix == ".png"
            )
        except OSError:
            return False

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR accuracy.

        Note: Apple Vision typically doesn't need preprocessing,
        but this can be useful for low-quality images.
        """
        logger.debug("Preprocessing image for OCR")

        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)

        # Scale up small images
        min_dimension = min(image.size)
        if min_dimension < 300:
            scale_factor = 300 / min_dimension
            new_size = (
                int(image.size[0] * scale_factor),
                int(image.size[1] * scale_factor),
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"Scaled image to {new_size}")

        return image
