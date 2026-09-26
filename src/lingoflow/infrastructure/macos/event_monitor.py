"""Own and release AppKit mouse monitors without retaining a window."""

from weakref import WeakMethod

from lingoflow.utils.logger import get_logger

logger = get_logger(__name__)


class OutsideClickMonitor:
    def __init__(self, api=None):
        self._api = api
        self._handles = []

    @property
    def active_count(self) -> int:
        return len(self._handles)

    def start(self, callback) -> None:
        self.close()
        owner_callback = WeakMethod(callback)

        def global_handler(event):
            target = owner_callback()
            if target is not None:
                target()

        def local_handler(event):
            global_handler(event)
            return event

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
            for register, handler in [
                (api.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_, global_handler),
                (api.NSEvent.addLocalMonitorForEventsMatchingMask_handler_, local_handler),
            ]:
                handle = register(mask, handler)
                if handle is not None:
                    self._handles.append(handle)
        except Exception as error:
            self.close()
            logger.debug("Could not install native mouse monitors: %s", error)

    def close(self) -> None:
        handles, self._handles = self._handles, []
        for handle in handles:
            try:
                self._api.NSEvent.removeMonitor_(handle)
            except Exception as error:
                logger.debug("Could not remove native mouse monitor: %s", error)
