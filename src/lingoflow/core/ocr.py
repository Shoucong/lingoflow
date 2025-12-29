"""
OCR service for LingoFlow. 

Handles screen capture and text extraction. 
- macOS: Uses Apple Vision framework
- Windows: Placeholder for future implementation, perhaps using Tesseract OCR
"""

import subprocess
import tempfile
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

from PIL import Image, ImageEnhance, ImageFilter

from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

if platform.system() == "Darwin":
    try:
        import Vision
        from Cocoa import NSURL
        VISION_AVAILABLE = True
    except ImportError:
        logger.warning("PyObjc not installed. Run: pip install pyobjc-framework-Vision")
        VISION_AVAILABLE = False
else:
    VISION_AVAILABLE = False


#==========================================================
# Data Types
#==========================================================

@dataclass
class CaptureRegion: 
    """Represents a screen region to capture"""

    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> Tuple[int, int ,int ,int]:
        """Return as (x,y,width,height) tuple"""
        return (self.x, self.y, self.width, self.height)

@dataclass
class OCRResult:
    """Result of an OCR operation."""

    text:str
    confidence: Optional[float] = None
    source_image_path: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


#==========================================================
# Exceptions
#==========================================================

class OCRError(Exception):
    """Base exception for OCR operations."""
    pass

class ScreenCaptureError(OCRError):
    """Failed to capture screen region"""
    pass

class VisionError(OCRError):
    """Apple Vision framework error."""
    pass


#==========================================================
# OCT Service
#==========================================================


class OCRService:
    """
    Screen capture and OCR text extraction service

    Platform support:
    - macOS: Native Apple Vision 
    - Windows: Implement in future

    Example: 
        ocr = OCRService()

        # Capture and extract in one step
        result = ocr.capture_and_extract(region)
        print(result.text)

        # Or extract from existing image
        result = ocr.extract_text(Path("/path/to/image.png"))
    """
    
    # Language mapping from Teseract codes -> Apple Vision 
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
        self._temp_dir = Path(tempfile.gettempdir()) / "lingoflow"
        self._temp_dir.mkdir(exist_ok=True)
        self._system = platform.system()

        # Verify OCR backend availability
        self._verify_ocr_backend()

        logger.info(
            f"OCRService initialized on {self._system}"
            f"language: {self.settings.orc.language}"
        )

    #==========================================================
    # Public Methods
    #==========================================================

    def extract_text(self, image_path: Path) -> OCRResult: 
        """
        Extract text from an image file. 

        Uses Apple Vision on macOS

        Args:
            image_path: Path to the image_file
        
        Returns: 
            OCRResult with extracted text
        """
        logger.debug(f"Extracting text from: {image_path}")

        if not image_path.exists():
            return OCRResult(
                text="",
                success=False,
                error_message=f"Image file not found: {image_path}",
            )
        
        try:
            if self._system == "Darwin":
                return self._extract_text_apple_vision(image_path)
            elif self._system == "Linux":
                return self._extract_text_linux(image_path)
            elif self._system =="Windows":
                return self._extract_text_windows(image_path)
            else:
                return OCRResult(
                    text="",
                    success=False,
                    error_message=f"Unsupported platform: {self._system}",
                )
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return OCRResult(text="", success=False, error_message=e)
    
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
        output_path = self._temp_dir / "capture.png"

        logger.debug(f"Capturing region: {region}")

        try: 
            if self._system == "Darwin":
                self._capture_macos(region, output_path)
            elif self._system == "Linux":
                self._capture_linux(region, output_path)
            elif self._system == "Windows":
                self._capture_windows(region, output_path)
            else:
                raise ScreenCaptureError(f"Unsupported platform: {self._system}")
            
            if not output_path.exists():
                raise ScreenCaptureError(f"Screenshot file was not created")
        
            logger.info(f"Screen captured: {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            raise ScreenCaptureError(f"Failed to capture screen: {e}") from e
        
    def capture_interactive(self) -> Optional[Path]:
        """
        Let user interactively select a screen region to capture. 

        Returns: 
            Path to captured image, or None if canceled
        """
        output_path = self._temp_dir / "capture.png"

        logger.info("Starting interactive screen capture")

        try:
            if self._system == "Darwin": 
                return self._capture_interactive_macos(output_path)
            elif self._system == "Linux":
                return self._capture_interactive_linux(output_path)
            elif self._system == "Windows":
                return self._capture_interactive_windows(output_path)
            else:
                logger.error(f"Unsupported platform: {self._system}")
                return None
        except Exception as e:
            logger.error(f"Interactive capture failed: {e}")
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
            
            return self.extract_text(image_path)

        except ScreenCaptureError as e:
            return OCRResult(text="", success=False, error_message=str(e))
    
    def get_available_languages(self) -> List[str]:
        """
        Get list of avaiable OCR languages.

        Returns: 
            List of language codes
        """
        if self._system == "Darwin":
            # apple vision supports natively
            return list(self.LANGUAGE_MAP.keys())
        else:
            # TODO: Query Tesseract for available languages
            return []
    
    def update_settings(self, settings: AppSettings) -> None:
        """Update service with new settings"""
        self.settings = settings
        logger.info(f"OCR settings updated, language: {settings.ocr.language}")
    

    #==========================================================
    # macOS implementation
    #==========================================================

    def _extract_text_apple_vision(self, image_path: Path) -> OCRResult:
        """
        Extract text using Apple's Vision framework.
        
        Provides excellent accuracy for CJK (Chinese, Japanese, Korean) text
        without requiring Tesseract installation.
        """
        if not VISION_AVAILABLE:
            return OCRResult(
                text="",
                success=False,
                error_message="Apple Vision not available. Install: pip install pyobjc-framework-Vision",
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
            success, error = request_handler.performRequests_error_([request], None)
            
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
                f"Apple Vision extracted {len(text)} chars "
                f"(confidence: {avg_confidence:.2%})"
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
        lang = self.settings.orc.language

        if lang in self.LANGUAGE_MAP:
            return self.LANGUAGE_MAP[lang]

        # default
        logger.warning(f"Unknown languages '{lang}', defaulting to en-US + zh-Hans")
        return ["en-US", "zh-Hans"]
    
    #==========================================================
    # macOS: Screen Capture
    #==========================================================
    
    def _capture_macos(self, region: CaptureRegion, output_path: Path) -> None:
        """
        Capture screen region on macOS using screencapture.
        """
        subprocess.run(
            [
                "screencapture",
                "-x",
                "-R", f"{region.x}, {region.y}, {region.width}, {region.height}",
                str(output_path)
            ],
            check=True,
        )

    def _capture_interactive_macos(self, output_path: Path) -> Optional[Path]:
        """
        Interactive screen capture on macOS. 
        """
        subprocess.run(
            ["screencapture", "-i", "-s", "-x", str(output_path)]
        )

        if output_path.exists():
            logger.info(f"Interactive capture saved: {output_path}")
            return output_path
        else:
            logger.info(f"Interactive capture cancelled by user")
    
    #==========================================================
    # Linux
    #==========================================================
    def _extract_text_linux(self, image_path: Path) -> OCRResult:
        """Extract text on Linux. TODO: Implement with Tesseract."""
        # TODO: Implement Tesseract-based OCR for Linux
        return OCRResult(
            text="",
            success=False,
            error_message="Linux OCR not yet implemented",
        )

    def _capture_linux(self, region: CaptureRegion, output_path: Path) -> None:
        """Capture screen region on Linux. TODO: Implement."""
        # TODO: Implement with gnome-screenshot or scrot
        raise ScreenCaptureError("Linux screen capture not yet implemented")

    def _capture_interactive_linux(self, output_path: Path) -> Optional[Path]:
        """Interactive capture on Linux. TODO: Implement."""
        # TODO: Implement with gnome-screenshot or scrot
        logger.error("Linux interactive capture not yet implemented")
        return None
    
    # -------------------------------------------------------------------------
    # Windows: Placeholder Implementation
    # -------------------------------------------------------------------------

    def _extract_text_windows(self, image_path: Path) -> OCRResult:
        """Extract text on Windows. TODO: Implement with Tesseract or Windows OCR."""
        # TODO: Implement with Tesseract or Windows.Media.Ocr
        return OCRResult(
            text="",
            success=False,
            error_message="Windows OCR not yet implemented",
        )

    def _capture_windows(self, region: CaptureRegion, output_path: Path) -> None:
        """Capture screen region on Windows. TODO: Implement."""
        # TODO: Implement with PowerShell or pyautogui
        raise ScreenCaptureError("Windows screen capture not yet implemented")

    def _capture_interactive_windows(self, output_path: Path) -> Optional[Path]:
        """Interactive capture on Windows. TODO: Implement."""
        # TODO: Implement with Snipping Tool or similar
        logger.error("Windows interactive capture not yet implemented")
        return None

    #==========================================================
    # Utility Methods
    #==========================================================

    def _verify_ocr_backend(self) -> None:
        """Verify OCR backend is avaiable for current platform"""
        if self._system == "Darwin":
            if VISION_AVAILABLE:
                logger.debug("Apple Vision framework avaiable")
            else:
                logger.warning(
                    "Apple Vision not available. "
                    "Install PyObjC: pip install pyobjc-framework-Vision"
                )
        else:
            logger.info(f"OCR not yet implemented for {self._system}")
        
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

        