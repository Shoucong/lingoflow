"""
Global hotkey manager for LingoFlow.

Handles system-wide keyboard shortcuts using pynput.
"""

import platform
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional, Set

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

IS_MACOS = platform.system() == "Darwin"

# ==========================================================
# Data Types
# ==========================================================

class HotkeyAction(Enum):
    """Predifined hotkey actions."""
    TRANSLATE = "translate"
    OCR = "ocr"
    PRONOUNCE = "pronounce"
    WORD_LOOKUP = "word_lookup"

@dataclass
class Hotkey:
    """Represents a registered hotkey."""

    action: HotkeyAction
    keys: frozenset
    key_string: str
    callback: Callable[[], None]
    description: str = ""
    # Track if currently held to prevent repeat-span
    is_pressed: bool = False


# =============================================================================
# macOS Virtual Key Code Mapping
# =============================================================================

# On macOS, Option+letter produces special characters (e.g., Option+D = ∂)
# We need to map virtual key codes to match letters regardless of modifiers
# These are macOS virtual key codes for letter keys
MACOS_VK_TO_LETTER = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x",
    8: "c", 9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r",
    16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
    31: "o", 32: "u", 34: "i", 35: "p", 37: "l", 38: "j", 40: "k",
    41: ";", 43: ",", 45: "n", 46: "m", 47: ".", 50: "`",
}

LETTER_TO_MACOS_VK = {v: k for k, v in MACOS_VK_TO_LETTER.items()}


# ==========================================================
# Hotkey Manager
# ==========================================================

class HotkeyManager:
    """
    Global hotkey manager using pynput.

    Uses pynput's native hotkey parsing for robust cross-platform support. 

    Example: 
        manager = HotkeyManager()

        manager.register_hotkey(
            HotkeyAction.TRANSLATE,
            "<alt>+d",
            callback=on_translate_triggered,
        )
        manager.start()
        # ...app runs ...
        manager.stop()
    """

    def __init__(self, settings: Optional[AppSettings] = None):
        """
        Initialize the hotkey manager,

        Args:
            settings: App settings (loads from disks if not provided).
        """
        self.settings = settings or AppSettings.load()
        
        self._hotkeys: Dict[HotkeyAction, Hotkey] = {}
        self._pressed_keys: Set = set()
        self._pressed_vks: Set[int] = set()
        self._listener: Optional[keyboard.Listener] = None
        self._running = False
        self._lock = threading.Lock()

        logger.info("HotkeyManager initialized.")
    
    # ==========================================================
    # Public Methods
    # ==========================================================

    def register(
            self, 
            action: HotkeyAction,
            hotkey_str: str,
            callback: Callable[[], None],
            description: str = "",
    ) -> bool:
        """
        Register a hotkey. 

        Uses pynput's native parser for robust key handling. 

        Args:
            action: The action this hotkey triggers.
            hotkey_str: Hotkey string like "<alt>+d".
            callback: Function to call when hotkey is triggered.
            description: Human-readable description.
        
        Returns:
            True if registered successfully
        """
        try:
            # Use pynput's native parser - handles <cmd>, <ctrl>, <alt> etc
            key_combo = keyboard.HotKey.parse(hotkey_str)
            keys = frozenset(key_combo)

            hotkey = Hotkey(
                action=action,
                keys=keys,
                key_string=hotkey_str,
                callback=callback,
                description=description,
            )

            with self._lock:
                self._hotkeys[action] = hotkey
            
            readable = self._format_hotkey_display(hotkey_str)
            logger.info(f"Registered hotkey: {readable} -> {action.value}")
            return True
        
        except ValueError as e:
            logger.error(f"Invalid hotkey format '{hotkey_str}': {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to register hotkey '{hotkey_str}': {e}")
            return False 
    
    def unregister(self, action: HotkeyAction) -> bool:
        """
        Unregister a hotkey. 

        Args:
            action: The action to unregister

        Returns:
            True if unregistered successfully
        """
        with self._lock:
            if action in self._hotkeys:
                del self._hotkeys[action]
                logger.info(f"Unregistered hotkey for: {action.value}")
                return True
        return False
    
    def update_hotkey(self, action: HotkeyAction, new_hotkey_str: str) -> bool:
        """
        Update an existing hotkey's key combination. 

        Args: 
            action: The action to update
            new_hotkey_str: New hotkey string
        
        Returns:
            True if updated successfully
        """
        with self._lock:
            if action in self._hotkeys:
                old_hotkey = self._hotkeys[action]
                return self.register(
                    action, 
                    new_hotkey_str,
                    old_hotkey.callback,
                    old_hotkey.description
                )
        return False
    
    def start(self) -> None:
        """Start listening for hotkeys in background thread."""
        if self._running:
            logger.warning("HotkeyManager already running.")
            return 
    
        self._running = True
        self._pressed_keys.clear()
        self._pressed_vks.clear()

        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

        logger.info(
            "HotkeyManager started. "
            "(Ensure 'Input Monitoring' permission is granted on macOS.)"
        )
    
    def stop(self) -> None: 
        """Stop listening for hotkeys."""
        self._running = False

        if self._listener:
            self._listener.stop()
            self._listener = None
        
        self._pressed_keys.clear()
        self._pressed_vks.clear()
        logger.info("HotkeyManager stopped.")
    
    def is_running(self) -> bool:
        """Check if the manager is currently listening."""
        return self._running

    def get_registered_hotkeys(self) -> Dict[HotkeyAction, str]:
        """
        Get all registered hotkeyts as readable strings. 

        Returns: 
            Dict mapping action to hotkey display string. 
        """
        with self._lock:
            return {
                action: self._format_hotkey_display(hotkey.key_string)
                for action, hotkey in self._hotkeys.items()
            }
    
    def update_settings(self, settings: AppSettings) -> None:
        """
        Update the settings reference.

        Args:
            settings: New app settings.
        """
        self.settings = settings    

        # Update translate hotkey if regisited
        if HotkeyAction.TRANSLATE in self._hotkeys:
            self.update_hotkey(HotkeyAction.TRANSLATE, settings.hotkeys.translate)
        
        # Update OCR hotkey if registered
        if HotkeyAction.OCR in self._hotkeys:
            self.update_hotkey(HotkeyAction.OCR, settings.hotkeys.ocr)
        
        logger.info("Hotkey settting updated.")
    
    # ==========================================================
    # Private Methods
    # ==========================================================

    def _on_key_press(self, key) -> None:
        """Handle key press event."""
        canonical_key = self._listener.canonical(key)
        self._pressed_keys.add(canonical_key)

        # Update: on Macos, we should check virtual key codes to prevent ∂ß etc. 
        if IS_MACOS and isinstance(key, KeyCode) and key.vk is not None:
            self._pressed_vks.add(key.vk)

        self._check_hotkeys()
    
    def _on_key_release(self, key) -> None:
        """Handle key release event."""
        canonical_key = self._listener.canonical(key)
        self._pressed_keys.discard(canonical_key)   

        # Clear virtual key code
        if IS_MACOS and isinstance(key, KeyCode) and key.vk is not None:
            self._pressed_vks.discard(key.vk)

        # Reset 'is_pressed' for hotkeys containing this key
        with self._lock:
            for hotkey in self._hotkeys.values():
                if canonical_key in hotkey.keys:
                    hotkey.is_pressed = False
                # Also check vitural key code
                if IS_MACOS and isinstance(key, KeyCode) and key.vk is not None:
                    if self._vk_matches_any_key(key.vk, hotkey.keys):
                        hotkey.is_pressed = False
    
    def _check_hotkeys(self) -> None: 
        """Check if any registered hotkey is pressed."""
        with self._lock:
            for action, hotkey in self._hotkeys.items():
                if self._hotkey_matches(hotkey.keys):
                    # Prevent repeat triggering while held
                    if not hotkey.is_pressed:
                        hotkey.is_pressed = True
                        logger.debug(f"Hotkey triggered: {hotkey.key_string}: {action.value}")

                        threading.Thread(
                            target=self._safe_callback,
                            args=(hotkey.callback, action),
                            daemon=True,
                        ).start()
    
    def _hotkey_matches(self, required_keys: frozenset) -> bool:
        """
        Check if required keys are currently pressed.
        
        On macOS, uses virtual key codes to handle Option+letter combinations.
        """
        for required_key in required_keys:
            if required_key in self._pressed_keys:
                # Direct match (works for modifiers and regular keys)
                continue
            elif IS_MACOS and isinstance(required_key, KeyCode):
                # On macOS, check if the virtual key code matches
                if required_key.char and required_key.char.lower() in LETTER_TO_MACOS_VK:
                    expected_vk = LETTER_TO_MACOS_VK[required_key.char.lower()]
                    if expected_vk in self._pressed_vks:
                        continue
                # Also check by vk directly
                if required_key.vk is not None and required_key.vk in self._pressed_vks:
                    continue
            # Key not matched
            return False
        return True
    
    def _vk_matches_any_key(self, vk: int, keys: frozenset) -> bool:
        """Check if a virtual key code matches any key in the set."""
        for key in keys:
            if isinstance(key, KeyCode):
                if key.vk == vk:
                    return True
                if key.char and key.char.lower() in LETTER_TO_MACOS_VK:
                    if LETTER_TO_MACOS_VK[key.char.lower()] == vk:
                        return True
        return False
    
    def _safe_callback(self, callback: Callable, action: HotkeyAction) -> None:
        """Execute callback safely with error handling."""
        try: 
            callback()
        except Exception as e:
            logger.error(f"Error in hotkey callback for {action.value}: {e}")
    
    def _format_hotkey_display(self, hotkey_str: str) -> str:
        """
        Format hotkey string for display. 

        Converts "<alt>+d" to "Alt + D" for UI display. 
        """
        # Simple formatting for common cases
        display = hotkey_str
        replacements = [
            ("<alt>", "Alt"),
            ("<ctrl>", "Ctrl"),
            ("<cmd>", "Cmd"),
            ("<shift>", "Shift"),
            ("<space>", "Space"),
            ("<enter>", "Enter"),
        ]
        for old, new in replacements:
            display = display.replace(old, new)
        
        # Capitialize letter keys
        parts = display.split("+")
        parts = [p.capitalize() if len(p)==1 else p for p in parts]
        return "+".join(parts)

    # ==========================================================
    # Convenience Function
    # ==========================================================

def create_default_hotkey_manager(
    on_translate: Callable[[], None], 
    on_ocr: Callable[[], None], 
    settings: Optional[AppSettings] = None,
) -> HotkeyManager:
    """
    Create a hotkey manager with default bindings. 

    Args:
        on_translate: Callback for translate hotkey. 
        on_ocr: Callback for OCR hotkey
        settings: App settings (optional)
    
    Returns:
        Configured HotkeyManager ready to start. 
    """
    settings = settings or AppSettings.load()
    manager = HotkeyManager(settings=settings)

    manager.register(
        HotkeyAction.TRANSLATE,
        settings.hotkeys.translate,
        on_translate,
        description="Translate selected text",
    )

    manager.register(
        HotkeyAction.OCR,
        settings.hotkeys.ocr,
        on_ocr,
        description="Capture screen region for OCR",
    )
    return manager