"""Apple Vision request lifecycle, independent of screenshot acquisition."""

import threading
from pathlib import Path

from lingoflow.core.errors import VisionError
from lingoflow.core.models import OCRResult
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import Vision
    from Cocoa import NSURL

    VISION_AVAILABLE = True
except ImportError:
    logger.warning("PyObjc not installed. Run: pip install pyobjc-framework-Vision")
    VISION_AVAILABLE = False


class VisionRecognizer:
    def __init__(self):
        self._operation_lock = threading.Lock()
        self._vision_request = None

    def cancel(self):
        with self._operation_lock:
            request = self._vision_request
        if request is not None:
            request.cancel()

    def recognize(self, image_path: Path, languages: list[str], cancel_check=None) -> OCRResult:
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

            # Set recognition languages; automatic detection (macOS 13+) keeps
            # English-only captures accurate when a CJK language is listed first.
            apple_languages = languages
            request.setRecognitionLanguages_(apple_languages)
            if hasattr(request, "setAutomaticallyDetectsLanguage_"):
                request.setAutomaticallyDetectsLanguage_(True)

            logger.debug(f"Vision request with languages: {apple_languages}")

            # Perform OCR
            with self._operation_lock:
                self._vision_request = request
            try:
                if cancel_check and cancel_check():
                    return OCRResult(text="", cancelled=True)
                success, error = request_handler.performRequests_error_([request], None)
            finally:
                with self._operation_lock:
                    self._vision_request = None

            if cancel_check and cancel_check():
                return OCRResult(text="", cancelled=True)

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
