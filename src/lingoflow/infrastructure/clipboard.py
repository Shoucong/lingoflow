"""
Clipboard operations for LingoFlow. 

Handles getting selected text and clipboard management. 
"""

import platform
import subprocess
import time
from typing import Optional

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

# ===========================================================
# Platform Detection
# ===========================================================

SYSTEM = platform.system()

# ===========================================================
# Excetions
# ===========================================================

class ClipboardError(Exception):
    """Base exception for clipboard operations."""

    pass

class ClipboardEmptyError(ClipboardError):
    """Clipboard is empty or contains non-text content."""

    pass

# ===========================================================
# Clipboad Manager
# ===========================================================

class ClipboardManager:
    """
    Cross-platform clipboard operations. 

    Handles: 
    - Getting current clipboard text
    - Setting clipboard text
    - Getting selected text (simulates copy, then restores clipboard)

    Example: 
        clipboard = ClipboardManager()

        # Get whatever selected
        selected = clipboard.get_selected_text()

        # Copy translation result
        clipboard.set_text("翻译结果“)
    """

    def __init__(self):
        """Initialize the clipboard manager."""
        logger.debug(f"ClipboardManager initialized on {SYSTEM}")

    # ==========================================================
    # Public Methods
    # ==========================================================

    def get_text(self) -> Optional[str]:
        """
        Get current text from clipboard. 

        Returns:
            Clipboard text, or None if empty/non-text
        """
        try:
            if SYSTEM == "Darwin":
                return self._get_text_macos()
            elif SYSTEM == "Windows":
                return self._get_text_windows()
            elif SYSTEM == "Linux":
                return self._get_text_linux()
            else:
                logger.warning(f"Unsupported platform: {SYSTEM}")
                return None
        except Exception as e:
            logger.error(f"Failed to get clipboard text: {e}")
            return None
    
    def set_text(self, text: str) -> bool:
        """
        Set clipboard text. 

        Args: 
            text: Text to copy to clipboard

        Returns:
            True if successful, False otherwise
        """
        try:
            if SYSTEM == "Darwin":
                return self._set_text_macos(text)
            elif SYSTEM == "Windows":
                return self._set_text_windows(text)
            elif SYSTEM == "Linux":
                return self._set_text_linux(text)
            else:
                logger.warning(f"Unsupported platform: {SYSTEM}")
                return False
        except Exception as e:
            logger.error(f"Failed to set clipboard text: {e}")
            return False
    
    def get_selected_text(self) -> Optional[str]:
        """
        Get currently selected text from any application. 
        
        This works by:
        1. Saving current clipboard content
        2. Simulating Cmd + C
        3. Reading the new clipboard content
        4. Restoring the original clipboard

        Returns:
            Selected text, or None if nothing selected
        """
        logger.debug("Getting selected text")

        # Save current clipboard
        original_clipboard = self.get_text()

        # Clear clipboard to detect if copy worked
        self.set_text("")

        # Small delay to ensure clipboard is cleared
        time.sleep(0.05)

        # Simulate copy command
        self._simulate_copy()

        # wait 0.1s for clipboard to update
        time.sleep(0.1)

        # Get the selected text
        selected_text = self.get_text()

        # Restore origninal clipboard
        if original_clipboard:
            self.set_text(original_clipboard)
        
        if selected_text:
            logger.debug(f"Got selected text: {len(selected_text)} chars")
        else:
            logger.debug("No text selected")
        
        return selected_text
    
    # ==========================================================
    # macOS Implementation
    # ==========================================================

    def _get_text_macos(self) -> Optional[str]:
        """Get clipboard text on macOS using pbpaste."""
        result = subprocess.run(
            ['pbpaste'],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
        return None
    
    def _set_text_macos(self, text: str) -> bool:
        """Set clipboard text on macOS using pbcopy."""
        result = subprocess.run(
            ['pbcopy'],
            input=text,
            text=True,
        )
        return result.returncode == 0
    
    def _simulate_copy_macos(self) -> None:
        """Simulate Cmd+C on macOS using osascript."""
        script = """
        tell application "System Events"
            keystroke "c" using command down
        end tell
        """
        subprocess.run(
            ['oascrupt', "-e", script],
            capture_output=True,
        )

    # ==========================================================
    # Windows Implementation
    # ==========================================================

    def _get_text_windows(self) -> Optional[str]:
        return None
    
    def _set_text_windows(self, text: str) -> bool:
        return None
    
    def _simulate_copy_windows(self) -> None:
        pass

    # ==========================================================
    # Linux Implementation
    # ==========================================================

    def _get_text_linux(self) -> Optional[str]:
        return None
    
    def _set_text_linux(self, text: str) -> bool:
        return None
    
    def _simulate_copy_linux(self) -> None:
        pass

    # ==========================================================
    # Platform Dis[atcher
    # ==========================================================
    
    def _simulate_copy(self) -> None:
        """Simulate copy command based on platform."""

        if SYSTEM == "Darwin":
            self._simulate_copy_macos()
        elif SYSTEM == "Windows":
            self._simulate_copy_windows()
        elif SYSTEM == "Linux":
            self._simulate_copy_linux()
        else:
            logger.warning(f"Cannot simulate copy on {SYSTEM}")
    