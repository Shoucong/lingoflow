"""
OCR service for LingoFlow.

Handles screen capture and text extraction.
Uses Apple Vision and macOS screencapture.
"""

import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

import objc
from PIL import Image, ImageEnhance, ImageFilter

from lingoflow.config.constants import OCR_CAPTURE_DIR
from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import Vision
    from Cocoa import NSURL

    VISION_AVAILABLE = True
except ImportError:
    logger.warning("PyObjc not installed. Run: pip install pyobjc-framework-Vision")
    VISION_AVAILABLE = False


# ==========================================================
# Data Types
# ==========================================================


@dataclass
class CaptureRegion:
    """Represents a screen region to capture"""

    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> Tuple[int, int, int, int]:
        """Return as (x,y,width,height) tuple"""
        return (self.x, self.y, self.width, self.height)


@dataclass
class OCRResult:
    """Result of an OCR operation."""

    text: str
    confidence: Optional[float] = None
    source_image_path: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    cancelled: bool = False


# ==========================================================
# Exceptions
# ==========================================================


class OCRError(Exception):
    """Base exception for OCR operations."""

    pass


class ScreenCaptureError(OCRError):
    """Failed to capture screen region"""

    pass


class VisionError(OCRError):
    """Apple Vision framework error."""

    pass


# ==========================================================
# OCR Service
# ==========================================================


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
        "eng+chi_sim": ["en-US", "zh-Hans"],
        "eng+jpn": ["en-US", "ja-JP"],
    }

    def __init__(self, settings: Optional[AppSettings] = None):
        """
        Initialize the OCR service

        Args:
            settings: App settings (loads from disk if not provided)
        """
        self.settings = settings or AppSettings.load()
        self._capture_dir = OCR_CAPTURE_DIR
        self._capture_gate = threading.Lock()
        self._vision_gate = threading.Lock()
        self._operation_lock = threading.Lock()
        self._capture_process = None
        self._capture_cancel = None
        self._vision_request = None
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

        try:
            with self._vision_gate, objc.autorelease_pool():
                if cancel_check and cancel_check():
                    return OCRResult(text="", cancelled=True)
                return self._extract_text_apple_vision(image_path)
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return OCRResult(text="", success=False, error_message=str(e))

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

    def _extract_text_apple_vision(self, image_path: Path) -> OCRResult:
        """
        Extract text using Apple's Vision framework.

        Provides strong accuracy for CJK (Chinese, Japanese, Korean) text.
        """
        if not VISION_AVAILABLE:
            return OCRResult(
                text="",
                success=False,
                error_message=(
                    "Apple Vision not available. " "Install: pip install pyobjc-framework-Vision"
                ),
            )

        try:
            # Create URL for the image
            input_url = NSURL.fileURLWithPath_(str(image_path))

            # Create request handler
            request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
                input_url, None
            )

            # Create text recognition request
            request = Vision.VNRecognizeTextRequest.alloc().init()

            # Configure for accuracy (vs speed)
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            # Set recognition languages
            apple_languages = self._get_apple_languages()
            request.setRecognitionLanguages_(apple_languages)

            logger.debug(f"Vision request with languages: {apple_languages}")

            # Perform OCR
            with self._operation_lock:
                self._vision_request = request
            try:
                success, error = request_handler.performRequests_error_([request], None)
            finally:
                with self._operation_lock:
                    self._vision_request = None

            if not success:
                error_msg = str(error) if error else "Unknown Vision error"
                raise VisionError(f"Vision request failed: {error_msg}")

            # Extract results
            results = request.results()
            if not results:
                logger.info("No text detected in image")
                return OCRResult(
                    text="",
                    confidence=0.0,
                    source_image_path=str(image_path),
                    success=True,
                )

            # Collect text and confidence from all observations
            extracted_lines = []
            total_confidence = 0.0

            for observation in results:
                # Get the best candidate for each detected text block
                candidates = observation.topCandidates_(1)
                if candidates:
                    candidate = candidates[0]
                    extracted_lines.append(candidate.string())
                    total_confidence += candidate.confidence()

            text = "\n".join(extracted_lines)
            avg_confidence = total_confidence / len(results) if results else 0.0

            logger.info(
                f"Apple Vision extracted {len(text)} chars " f"(confidence: {avg_confidence:.2%})"
            )

            return OCRResult(
                text=text,
                confidence=avg_confidence,
                source_image_path=str(image_path),
                success=True,
            )

        except VisionError:
            raise
        except Exception as e:
            logger.error(f"Apple Vision error: {e}")
            return OCRResult(text="", success=False, error_message=str(e))

    def _get_apple_languages(self) -> List[str]:
        """
        Get Apple Vision language identifiers from settings.

        Falls back to English + Chinese if language not mapped.
        """
        lang = self.settings.ocr.language

        if lang in self.LANGUAGE_MAP:
            return self.LANGUAGE_MAP[lang]

        # default
        logger.warning(f"Unknown languages '{lang}', defaulting to en-US + zh-Hans")
        return ["en-US", "zh-Hans"]

    # ==========================================================
    # macOS: Screen Capture
    # ==========================================================

    def cancel(self) -> None:
        """Cancel only this service's capture process and current Vision request."""
        with self._operation_lock:
            process, cancelled = self._capture_process, self._capture_cancel
            request = self._vision_request
        if cancelled:
            cancelled.set()
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        if request is not None:
            request.cancel()

    def _run_capture(self, arguments, timeout: float, cancel_check=None):
        while not self._capture_gate.acquire(timeout=0.05):
            if cancel_check and cancel_check():
                return subprocess.CompletedProcess(arguments, -1, "", "")
        process = None
        cancelled = threading.Event()
        try:
            if cancel_check and cancel_check():
                return subprocess.CompletedProcess(arguments, -1, "", "")
            process = subprocess.Popen(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._operation_lock:
                self._capture_process, self._capture_cancel = process, cancelled
            deadline = time.monotonic() + timeout
            while True:
                if cancelled.is_set() or (cancel_check and cancel_check()):
                    return subprocess.CompletedProcess(arguments, -1, "", "")
                if time.monotonic() >= deadline:
                    raise ScreenCaptureError("Screen capture timed out.")
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    if cancelled.is_set() or (cancel_check and cancel_check()):
                        return subprocess.CompletedProcess(arguments, -1, "", "")
                    return subprocess.CompletedProcess(
                        arguments, process.returncode, stdout, stderr
                    )
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process and process.poll() is None:
                process.kill()
                process.communicate()
            with self._operation_lock:
                self._capture_process = self._capture_cancel = None
            self._capture_gate.release()

    def _capture_macos(self, region: CaptureRegion, output_path: Path) -> None:
        result = self._run_capture(
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
        result = self._run_capture(
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
