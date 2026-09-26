"""
macOS clipboard and selected-text capture.

The app reads selected text by preserving the pasteboard, posting Cmd+C through
Quartz, reading the copied text, and restoring the original pasteboard.
"""

import threading
import time
from collections.abc import Callable
from typing import Any, Optional

import ApplicationServices
import objc
import Quartz
from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString, NSString, NSWorkspace

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class ClipboardError(Exception):
    """Base exception for clipboard operations."""


class ClipboardEmptyError(ClipboardError):
    """Clipboard is empty or contains non-text content."""


class ClipboardManager:
    """macOS pasteboard helper."""

    def __init__(self, pasteboard=None, copy_timeout: float = 0.6):
        self._pasteboard = (
            pasteboard if pasteboard is not None else NSPasteboard.generalPasteboard()
        )
        self._copy_timeout = copy_timeout
        self._selection_lock = threading.Lock()
        logger.debug("ClipboardManager initialized")

    def get_text(self) -> Optional[str]:
        """Get plain text from the macOS pasteboard."""
        try:
            pb = self._pasteboard
            content = pb.stringForType_(NSPasteboardTypeString)
            return content if content else None
        except Exception as e:
            logger.error(f"AppKit get_text error: {e}")
            return None

    def set_text(self, text: str) -> bool:
        """Set plain text on the macOS pasteboard."""
        try:
            pb = self._pasteboard
            pb.clearContents()
            ns_string = NSString.stringWithString_(text)
            return bool(pb.setString_forType_(ns_string, NSPasteboardTypeString))
        except Exception as e:
            logger.error(f"AppKit set_text error: {e}")
            return False

    def get_selected_text(self, cancel_check: Callable[[], bool] | None = None) -> Optional[str]:
        """Prefer Accessibility; fall back to a bounded, change-count guarded copy."""
        while not self._selection_lock.acquire(timeout=0.05):
            if cancel_check and cancel_check():
                return None
        try:
            with objc.autorelease_pool():
                if cancel_check and cancel_check():
                    return None
                text = self._get_accessibility_selection()
                if text:
                    return None if cancel_check and cancel_check() else text
                return self._copy_selection(cancel_check)
        finally:
            self._selection_lock.release()

    def _get_accessibility_selection(self) -> Optional[str]:
        try:
            system = ApplicationServices.AXUIElementCreateSystemWide()
            ApplicationServices.AXUIElementSetMessagingTimeout(system, 0.4)
            error, focused = ApplicationServices.AXUIElementCopyAttributeValue(
                system,
                ApplicationServices.kAXFocusedUIElementAttribute,
                None,
            )
            if error or focused is None:
                return None
            error, selected = ApplicationServices.AXUIElementCopyAttributeValue(
                focused,
                ApplicationServices.kAXSelectedTextAttribute,
                None,
            )
            if not error and selected:
                return str(selected)
        except Exception:
            logger.debug("Accessibility selection unavailable; trying copy fallback")
        return None

    @staticmethod
    def _frontmost_pid() -> int | None:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return int(app.processIdentifier()) if app else None

    def _copy_selection(self, cancel_check) -> Optional[str]:
        pb = self._pasteboard
        original_count = pb.changeCount()
        snapshot = self._snapshot_clipboard()
        if pb.changeCount() != original_count or (cancel_check and cancel_check()):
            return None
        source_pid = self._frontmost_pid()
        if not self._simulate_copy():
            return None
        # Never clear the pasteboard. Once copy is posted, finish the bounded
        # capture/restore even if canceled, to avoid leaving our copy behind.
        deadline = time.monotonic() + self._copy_timeout
        while time.monotonic() < deadline:
            copied_count = pb.changeCount()
            if copied_count != original_count:
                if source_pid != self._frontmost_pid():
                    return None
                text = self.get_text()
                restored = self._restore_clipboard(snapshot, expected_count=copied_count)
                if not restored or (cancel_check and cancel_check()):
                    return None
                return text
            time.sleep(0.01)
        return None

    def _snapshot_clipboard(self) -> list[list[tuple[Any, Any]]]:
        """Capture all current pasteboard item data for later restoration."""
        snapshot = []
        pb = self._pasteboard

        for item in pb.pasteboardItems() or []:
            item_snapshot = []
            for item_type in item.types() or []:
                data = item.dataForType_(item_type)
                if data is not None:
                    item_snapshot.append((item_type, data))
            if item_snapshot:
                snapshot.append(item_snapshot)

        return snapshot

    def _restore_clipboard(
        self,
        snapshot: list[list[tuple[Any, Any]]],
        expected_count: int | None = None,
    ) -> bool:
        """Restore a pasteboard snapshot created by _snapshot_clipboard."""
        try:
            pb = self._pasteboard
            if expected_count is not None and pb.changeCount() != expected_count:
                return False
            pb.clearContents()

            restored_items = []
            for item_snapshot in snapshot:
                item = NSPasteboardItem.alloc().init()
                for item_type, data in item_snapshot:
                    item.setData_forType_(data, item_type)
                restored_items.append(item)

            if restored_items:
                return bool(pb.writeObjects_(restored_items))
            return True
        except Exception as e:
            logger.error(f"AppKit restore clipboard error: {e}")
            return False

    def _simulate_copy(self) -> bool:
        """Simulate Cmd+C from this app process using Quartz key events."""
        try:
            if (
                hasattr(Quartz, "CGPreflightPostEventAccess")
                and not Quartz.CGPreflightPostEventAccess()
            ):
                logger.warning(
                    "Cannot post Cmd+C. "
                    "Grant Accessibility permission to LingoFlow, then restart the app."
                )
                return False

            key_code_c = 8
            key_down = Quartz.CGEventCreateKeyboardEvent(None, key_code_c, True)
            key_up = Quartz.CGEventCreateKeyboardEvent(None, key_code_c, False)
            if key_down is None or key_up is None:
                logger.warning("Could not create Cmd+C keyboard events")
                return False

            Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventSetFlags(key_up, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
            time.sleep(0.02)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
            return True
        except Exception as e:
            logger.error(
                "Failed to post Cmd+C. "
                "Check macOS Accessibility permission for LingoFlow. "
                f"Error: {e}"
            )
            return False
