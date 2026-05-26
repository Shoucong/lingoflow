"""
Native macOS global hotkey manager.

LingoFlow is currently macOS-first, so hotkeys are handled through Quartz event
taps. The tap consumes the trigger key and waits for required modifiers to be
released before dispatching the app action, which avoids leaking Option-modified
keystrokes into the foreground app.
"""

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

import Quartz

from lingoflow.config.settings import AppSettings
from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class HotkeyAction(Enum):
    """Predefined hotkey actions."""

    TRANSLATE = "translate"
    OCR = "ocr"
    PRONOUNCE = "pronounce"
    WORD_LOOKUP = "word_lookup"


@dataclass
class Hotkey:
    """A registered macOS hotkey."""

    action: HotkeyAction
    key_code: int
    modifiers: int
    key_string: str
    callback: Callable[[], None]
    description: str = ""


KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "`": 50,
    "space": 49,
    "tab": 48,
    "return": 36,
    "enter": 36,
    "escape": 53,
    "esc": 53,
}

MODIFIER_FLAGS = {
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "shift": Quartz.kCGEventFlagMaskShift,
}

MODIFIER_DISPLAY = {
    Quartz.kCGEventFlagMaskAlternate: "Option",
    Quartz.kCGEventFlagMaskCommand: "Cmd",
    Quartz.kCGEventFlagMaskControl: "Ctrl",
    Quartz.kCGEventFlagMaskShift: "Shift",
}


class HotkeyManager:
    """Global hotkey manager backed by a native macOS Quartz event tap."""

    def __init__(self, settings: Optional[AppSettings] = None):
        self.settings = settings or AppSettings.load()
        self._hotkeys: Dict[HotkeyAction, Hotkey] = {}
        self._active_key_actions: Dict[int, HotkeyAction] = {}
        self._pending_actions: Dict[HotkeyAction, Hotkey] = {}
        self._listener_thread: Optional[threading.Thread] = None
        self._run_loop = None
        self._event_tap = None
        self._run_loop_source = None
        self._tap_callback = None
        self._started_event = threading.Event()
        self._running = False
        self._lock = threading.RLock()

        logger.info("Native macOS HotkeyManager initialized")

    def register(
        self,
        action: HotkeyAction,
        hotkey_str: str,
        callback: Callable[[], None],
        description: str = "",
    ) -> bool:
        """Register or replace a hotkey."""
        try:
            key_code, modifiers = self._parse_hotkey(hotkey_str)
        except ValueError as e:
            logger.error(f"Invalid hotkey '{hotkey_str}': {e}")
            return False

        with self._lock:
            self._hotkeys[action] = Hotkey(
                action=action,
                key_code=key_code,
                modifiers=modifiers,
                key_string=hotkey_str,
                callback=callback,
                description=description,
            )

        logger.info(
            f"Registered hotkey: {self._format_hotkey_display(hotkey_str)} -> {action.value}"
        )
        return True

    def unregister(self, action: HotkeyAction) -> bool:
        """Unregister a hotkey action."""
        with self._lock:
            removed = self._hotkeys.pop(action, None)
            self._pending_actions.pop(action, None)
            for key_code, active_action in list(self._active_key_actions.items()):
                if active_action == action:
                    del self._active_key_actions[key_code]

        if removed:
            logger.info(f"Unregistered hotkey for: {action.value}")
            return True
        return False

    def update_hotkey(self, action: HotkeyAction, new_hotkey_str: str) -> bool:
        """Update an existing hotkey while preserving its callback."""
        with self._lock:
            hotkey = self._hotkeys.get(action)
            if hotkey is None:
                return False

        return self.register(action, new_hotkey_str, hotkey.callback, hotkey.description)

    def start(self) -> None:
        """Start the native event tap listener."""
        if self._running:
            logger.warning("HotkeyManager already running")
            return

        self._started_event.clear()
        self._listener_thread = threading.Thread(
            target=self._run_event_tap,
            name="LingoFlowHotkeys",
            daemon=True,
        )
        self._listener_thread.start()

        if not self._started_event.wait(timeout=1.0):
            logger.warning("Timed out waiting for native hotkey listener to start")

    def stop(self) -> None:
        """Stop the native event tap listener."""
        self._running = False

        if self._event_tap is not None:
            Quartz.CGEventTapEnable(self._event_tap, False)

        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)

        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)

        self._listener_thread = None
        self._run_loop = None
        self._event_tap = None
        self._run_loop_source = None
        self._tap_callback = None
        self._active_key_actions.clear()
        self._pending_actions.clear()
        logger.info("HotkeyManager stopped")

    def is_running(self) -> bool:
        """Return whether the native listener is running."""
        return self._running

    def get_registered_hotkeys(self) -> Dict[HotkeyAction, str]:
        """Return registered hotkeys as display strings."""
        with self._lock:
            return {
                action: self._format_hotkey_display(hotkey.key_string)
                for action, hotkey in self._hotkeys.items()
            }

    def update_settings(self, settings: AppSettings) -> None:
        """Update hotkey settings."""
        self.settings = settings
        was_running = self._running
        if was_running:
            self.stop()

        if HotkeyAction.TRANSLATE in self._hotkeys:
            self.update_hotkey(HotkeyAction.TRANSLATE, settings.hotkeys.translate)
        if HotkeyAction.OCR in self._hotkeys:
            self.update_hotkey(HotkeyAction.OCR, settings.hotkeys.ocr)

        if was_running:
            self.start()

        logger.info("Hotkey settings updated")

    def _run_event_tap(self) -> None:
        """Create and run the Quartz event tap on its own run loop."""
        missing_permissions = []
        if (
            hasattr(Quartz, "CGPreflightListenEventAccess")
            and not Quartz.CGPreflightListenEventAccess()
        ):
            missing_permissions.append("Input Monitoring")
        if (
            hasattr(Quartz, "CGPreflightPostEventAccess")
            and not Quartz.CGPreflightPostEventAccess()
        ):
            missing_permissions.append("Accessibility")

        if missing_permissions:
            self._running = False
            self._started_event.set()
            logger.error(
                "Native hotkeys unavailable. Missing permission(s): "
                f"{', '.join(missing_permissions)}."
            )
            return

        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )

        self._tap_callback = self._handle_event
        self._event_tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._tap_callback,
            None,
        )

        if self._event_tap is None:
            self._running = False
            self._started_event.set()
            logger.error(
                "Could not create native hotkey event tap. "
                "Grant Accessibility and Input Monitoring permissions, then restart LingoFlow."
            )
            return

        self._run_loop = Quartz.CFRunLoopGetCurrent()
        self._run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._event_tap, 0)
        Quartz.CFRunLoopAddSource(
            self._run_loop,
            self._run_loop_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(self._event_tap, True)
        self._running = True
        self._started_event.set()

        logger.info("Native macOS hotkey listener started")
        Quartz.CFRunLoopRun()

        if self._run_loop and self._run_loop_source:
            Quartz.CFRunLoopRemoveSource(
                self._run_loop,
                self._run_loop_source,
                Quartz.kCFRunLoopCommonModes,
            )
        self._running = False

    def _handle_event(self, proxy, event_type, event, refcon):
        """Handle keyboard events from Quartz."""
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._event_tap is not None:
                Quartz.CGEventTapEnable(self._event_tap, True)
            return event

        if event_type == Quartz.kCGEventFlagsChanged:
            self._dispatch_ready_pending_actions(Quartz.CGEventGetFlags(event))
            return event

        if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            return event

        key_code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)

        if event_type == Quartz.kCGEventKeyDown:
            return None if self._handle_key_down(key_code, flags) else event

        return None if self._handle_key_up(key_code, flags) else event

    def _handle_key_down(self, key_code: int, flags: int) -> bool:
        """Return True when the key event should be consumed."""
        with self._lock:
            if key_code in self._active_key_actions:
                return True

            for hotkey in self._hotkeys.values():
                if hotkey.key_code == key_code and self._modifiers_match(flags, hotkey.modifiers):
                    self._active_key_actions[key_code] = hotkey.action
                    return True

        return False

    def _handle_key_up(self, key_code: int, flags: int) -> bool:
        """Return True when the key event should be consumed."""
        with self._lock:
            action = self._active_key_actions.pop(key_code, None)
            if action is None:
                return False

            hotkey = self._hotkeys.get(action)
            if hotkey is None:
                return True

            if self._modifiers_released(flags, hotkey.modifiers):
                self._dispatch(hotkey)
            else:
                self._pending_actions[action] = hotkey
            return True

    def _dispatch_ready_pending_actions(self, flags: int) -> None:
        """Dispatch actions whose modifiers have been released."""
        ready = []
        with self._lock:
            for action, hotkey in list(self._pending_actions.items()):
                if self._modifiers_released(flags, hotkey.modifiers):
                    ready.append(hotkey)
                    del self._pending_actions[action]

        for hotkey in ready:
            self._dispatch(hotkey)

    def _dispatch(self, hotkey: Hotkey) -> None:
        """Run a hotkey callback outside the event tap callback."""
        logger.debug(f"Hotkey triggered: {hotkey.key_string}: {hotkey.action.value}")
        threading.Thread(
            target=self._safe_callback,
            args=(hotkey.callback, hotkey.action),
            daemon=True,
        ).start()

    def _safe_callback(self, callback: Callable[[], None], action: HotkeyAction) -> None:
        """Execute a callback with logging."""
        try:
            callback()
        except Exception as e:
            logger.error(f"Error in hotkey callback for {action.value}: {e}")

    def _parse_hotkey(self, hotkey_str: str) -> tuple[int, int]:
        """Parse '<alt>+d' style settings into a macOS key code and modifier mask."""
        tokens = [token.strip().lower() for token in hotkey_str.split("+") if token.strip()]
        if not tokens:
            raise ValueError("empty hotkey")

        modifiers = 0
        key_code = None
        for token in tokens:
            token = token.removeprefix("<").removesuffix(">")
            if token in MODIFIER_FLAGS:
                modifiers |= MODIFIER_FLAGS[token]
            elif token in KEY_CODES:
                if key_code is not None:
                    raise ValueError("hotkey can contain only one non-modifier key")
                key_code = KEY_CODES[token]
            else:
                raise ValueError(f"unsupported key token '{token}'")

        if key_code is None:
            raise ValueError("hotkey must include a non-modifier key")
        if modifiers == 0:
            raise ValueError("hotkey must include at least one modifier")

        return key_code, modifiers

    def _modifiers_match(self, flags: int, required_modifiers: int) -> bool:
        """Return whether the required modifiers are currently held."""
        return (flags & required_modifiers) == required_modifiers

    def _modifiers_released(self, flags: int, required_modifiers: int) -> bool:
        """Return whether all modifiers needed by a hotkey have been released."""
        return (flags & required_modifiers) == 0

    def _format_hotkey_display(self, hotkey_str: str) -> str:
        """Format '<alt>+d' as 'Option+D' for menus and settings."""
        try:
            key_code, modifiers = self._parse_hotkey(hotkey_str)
        except ValueError:
            return hotkey_str

        parts = [label for flag, label in MODIFIER_DISPLAY.items() if modifiers & flag]
        key = next((name for name, code in KEY_CODES.items() if code == key_code), str(key_code))
        parts.append(key.upper() if len(key) == 1 else key.capitalize())
        return "+".join(parts)


def create_default_hotkey_manager(
    on_translate: Callable[[], None],
    on_ocr: Callable[[], None],
    settings: Optional[AppSettings] = None,
) -> HotkeyManager:
    """Create the app's default hotkey manager."""
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
