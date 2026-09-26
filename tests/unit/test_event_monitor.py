import gc
import weakref
from types import SimpleNamespace

from lingoflow.infrastructure.macos.event_monitor import OutsideClickMonitor


class FakeEvents:
    def __init__(self):
        self.handlers = {}
        self.fail_local = False

    def addGlobalMonitorForEventsMatchingMask_handler_(self, mask, handler):  # noqa: N802
        self.handlers["global"] = handler
        return "global"

    def addLocalMonitorForEventsMatchingMask_handler_(self, mask, handler):  # noqa: N802
        if self.fail_local:
            raise RuntimeError("Cannot register")
        self.handlers["local"] = handler
        return "local"

    def removeMonitor_(self, handle):  # noqa: N802
        del self.handlers[handle]


class Window:
    def clicked(self):
        pass


def monitor_for(events):
    return OutsideClickMonitor(
        SimpleNamespace(
            NSEvent=events,
            NSEventMaskLeftMouseDown=1,
            NSEventMaskRightMouseDown=2,
            NSEventMaskOtherMouseDown=4,
        )
    )


def test_monitor_does_not_retain_window_and_closes_all_handles():
    events = FakeEvents()
    monitor = monitor_for(events)
    window = Window()
    reference = weakref.ref(window)
    monitor.start(window.clicked)
    assert monitor.active_count == 2
    del window
    gc.collect()
    assert reference() is None
    events.handlers["global"](None)
    monitor.close()
    assert monitor.active_count == 0
    assert not events.handlers


def test_partial_monitor_registration_is_rolled_back():
    events = FakeEvents()
    events.fail_local = True
    monitor = monitor_for(events)
    window = Window()
    monitor.start(window.clicked)
    assert not events.handlers
    assert monitor.active_count == 0
