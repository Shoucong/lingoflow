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
