import gc
import os
import weakref
from types import SimpleNamespace

from lingoflow.infrastructure.macos.event_monitor import OutsideInteractionMonitor


class FakeEvents:
    def __init__(self):
        self.handlers = {}

    def addGlobalMonitorForEventsMatchingMask_handler_(self, mask, handler):  # noqa: N802
        self.handlers["global"] = handler
        return "global"

    def addLocalMonitorForEventsMatchingMask_handler_(self, mask, handler):  # noqa: N802
        raise AssertionError("Clicks inside LingoFlow must never count as outside clicks")

    def removeMonitor_(self, handle):  # noqa: N802
        del self.handlers[handle]


class FakeApp:
    def __init__(self, pid, policy=0):
        self.pid, self.policy = pid, policy

    def processIdentifier(self):  # noqa: N802
        return self.pid

    def activationPolicy(self):  # noqa: N802
        return self.policy


class FakeNotification:
    def __init__(self, app):
        self.app = app

    def userInfo(self):  # noqa: N802
        return {"app": self.app}


class FakeCenter:
    def __init__(self, fail=False):
        self.observers = {}
        self.fail = fail

    def addObserverForName_object_queue_usingBlock_(self, name, obj, queue, handler):  # noqa: N802
        if self.fail:
            raise RuntimeError("Cannot observe")
        self.observers["activation"] = handler
        return "activation"

    def removeObserver_(self, observer):  # noqa: N802
        del self.observers[observer]


class FakeWorkspace:
    def __init__(self, center, reading_pid=300):
        self.center = center
        self.reading_pid = reading_pid

    def notificationCenter(self):  # noqa: N802
        return self.center

    def menuBarOwningApplication(self):  # noqa: N802
        return FakeApp(self.reading_pid)


class Window:
    def __init__(self):
        self.clicks = 0
        self.switches = 0

    def clicked(self):
        self.clicks += 1

    def switched(self):
        self.switches += 1


def monitor_for(events, center):
    workspace = FakeWorkspace(center)
    api = SimpleNamespace(
        NSEvent=events,
        NSEventMaskLeftMouseDown=1,
        NSEventMaskRightMouseDown=2,
        NSEventMaskOtherMouseDown=4,
        NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace),
        NSWorkspaceApplicationKey="app",
        NSWorkspaceDidActivateApplicationNotification="activated",
        NSOperationQueue=SimpleNamespace(mainQueue=lambda: None),
    )
    return OutsideInteractionMonitor(api)


def test_monitor_does_not_retain_window_and_closes_all_handles():
    events, center = FakeEvents(), FakeCenter()
    monitor = monitor_for(events, center)
    window = Window()
    reference = weakref.ref(window)
    monitor.start(window.clicked, window.switched)
    assert monitor.active_count == 2
    assert monitor.reading_pid == 300
    del window
    gc.collect()
    assert reference() is None
    events.handlers["global"](None)
    center.observers["activation"](FakeNotification(FakeApp(200)))
    monitor.close()
    assert monitor.active_count == 0
    assert not events.handlers and not center.observers


def test_only_activating_another_regular_app_reports_a_switch():
    events, center = FakeEvents(), FakeCenter()
    monitor = monitor_for(events, center)
    window = Window()
    monitor.start(window.clicked, window.switched)
    notify = center.observers["activation"]
    notify(FakeNotification(FakeApp(os.getpid())))  # LingoFlow's own About/Settings
    notify(FakeNotification(FakeApp(300)))  # back to the app being read
    notify(FakeNotification(FakeApp(400, policy=1)))  # background UI agent
    assert window.switches == 0
    notify(FakeNotification(FakeApp(200)))
    assert window.switches == 1
    events.handlers["global"](None)
    assert window.clicks == 1
    monitor.close()


def test_partial_monitor_registration_is_rolled_back():
    events, center = FakeEvents(), FakeCenter(fail=True)
    monitor = monitor_for(events, center)
    window = Window()
    monitor.start(window.clicked, window.switched)
    assert not events.handlers
    assert monitor.active_count == 0
