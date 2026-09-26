"""Own and release AppKit observers for leaving a reading window, without retaining it.

Only interactions that belong to *other* applications count as leaving:

- a mouse press delivered to another app or the desktop (a global monitor never
  sees clicks inside LingoFlow's own windows, menus or status item), and
- another regular application becoming active, e.g. with Command-Tab.

Activations of LingoFlow itself (About, Settings, menus) and of background UI
agents are ignored, as is the application that owned the menu bar when the
window appeared: returning to the app being read is not a switch away from it.
"""

from __future__ import annotations

import os
from weakref import WeakMethod

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)

# NSApplicationActivationPolicyRegular; accessory/prohibited apps are UI agents.
_REGULAR_POLICY = 0


def is_reading_exit(activated_pid: int, policy: int, own_pid: int, reading_pid: int | None) -> bool:
    """Return whether an application activation means the user left the reading context."""
    return policy == _REGULAR_POLICY and activated_pid not in {own_pid, reading_pid}


class OutsideInteractionMonitor:
    def __init__(self, api=None):
        self._api = api
        self._handles = []
        self._observers = []
        self.reading_pid: int | None = None

    @property
    def active_count(self) -> int:
        return len(self._handles) + len(self._observers)

    def start(self, on_click, on_app_switch=None) -> None:
        self.close()
        click_target = WeakMethod(on_click)
        switch_target = WeakMethod(on_app_switch) if on_app_switch else None
        own_pid = os.getpid()

        def click_handler(_event):
            target = click_target()
            if target is not None:
                target()

        def activation_handler(notification):
            target = switch_target() if switch_target else None
            if target is None:
                return
            try:
                app = notification.userInfo()[api.NSWorkspaceApplicationKey]
                pid, policy = int(app.processIdentifier()), int(app.activationPolicy())
            except Exception as error:
                logger.debug("Ignoring unreadable activation notification: %s", error)
                return
            if is_reading_exit(pid, policy, own_pid, self.reading_pid):
                target()

        try:
            if self._api is None:
                import AppKit

                self._api = AppKit
            api = self._api
            mask = (
                api.NSEventMaskLeftMouseDown
                | api.NSEventMaskRightMouseDown
                | api.NSEventMaskOtherMouseDown
            )
            handle = api.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                mask, click_handler
            )
            if handle is not None:
                self._handles.append(handle)
            if switch_target is not None:
                workspace = api.NSWorkspace.sharedWorkspace()
                owner = workspace.menuBarOwningApplication()
                self.reading_pid = int(owner.processIdentifier()) if owner else None
                center = workspace.notificationCenter()
                observer = center.addObserverForName_object_queue_usingBlock_(
                    api.NSWorkspaceDidActivateApplicationNotification,
                    None,
                    api.NSOperationQueue.mainQueue(),
                    activation_handler,
                )
                if observer is not None:
                    self._observers.append(observer)
        except Exception as error:
            self.close()
            logger.debug("Could not install native interaction monitors: %s", error)

    def close(self) -> None:
        handles, self._handles = self._handles, []
        observers, self._observers = self._observers, []
        for handle in handles:
            try:
                self._api.NSEvent.removeMonitor_(handle)
            except Exception as error:
                logger.debug("Could not remove native mouse monitor: %s", error)
        for observer in observers:
            try:
                center = self._api.NSWorkspace.sharedWorkspace().notificationCenter()
                center.removeObserver_(observer)
            except Exception as error:
                logger.debug("Could not remove activation observer: %s", error)


# Backwards-compatible name used by earlier diagnostics.
OutsideClickMonitor = OutsideInteractionMonitor
