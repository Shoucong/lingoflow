"""
macOS clipboard and selected-text capture.

The app reads selected text by preserving the pasteboard, posting Cmd+C through
Quartz, reading the copied text, and restoring the original pasteboard.
"""

import time
from typing import Any, Optional

import Quartz
from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString, NSString

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class ClipboardError(Exception):
    """Base exception for clipboard operations."""


class ClipboardEmptyError(ClipboardError):
    """Clipboard is empty or contains non-text content."""


class ClipboardManager:
    """macOS pasteboard helper."""

    def __init__(self):
        logger.debug("ClipboardManager initialized")

    def get_text(self) -> Optional[str]:
        """Get plain text from the macOS pasteboard."""
        try:
            pb = NSPasteboard.generalPasteboard()
            content = pb.stringForType_(NSPasteboardTypeString)
            return content if content else None
        except Exception as e:
            logger.error(f"AppKit get_text error: {e}")
            return None

    def set_text(self, text: str) -> bool:
        """Set plain text on the macOS pasteboard."""
        try:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            ns_string = NSString.stringWithString_(text)
            return bool(pb.setString_forType_(ns_string, NSPasteboardTypeString))
        except Exception as e:
            logger.error(f"AppKit set_text error: {e}")
            return False

    def get_selected_text(self) -> Optional[str]:
        """Copy the current selection, read it, then restore the pasteboard."""
        logger.debug("Getting selected text")
        clipboard_snapshot = self._snapshot_clipboard()

        self.set_text("")
        time.sleep(0.05)

        copy_succeeded = self._simulate_copy()
        time.sleep(0.1)

        selected_text = self.get_text() if copy_succeeded else None
        self._restore_clipboard(clipboard_snapshot)

        if selected_text:
            logger.debug(f"Got selected text: {len(selected_text)} chars")
        else:
            logger.debug("No text selected")

        return selected_text

    def _snapshot_clipboard(self) -> list[list[tuple[Any, Any]]]:
        """Capture all current pasteboard item data for later restoration."""
        snapshot = []
        pb = NSPasteboard.generalPasteboard()

        for item in pb.pasteboardItems() or []:
            item_snapshot = []
            for item_type in item.types() or []:
                data = item.dataForType_(item_type)
                if data is not None:
                    item_snapshot.append((item_type, data))
            if item_snapshot:
                snapshot.append(item_snapshot)

        return snapshot

    def _restore_clipboard(self, snapshot: list[list[tuple[Any, Any]]]) -> bool:
        """Restore a pasteboard snapshot created by _snapshot_clipboard."""
        try:
            pb = NSPasteboard.generalPasteboard()
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
