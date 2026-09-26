"""Register against real AppKit selectors; fakes alone cannot catch a wrong selector."""

import sys

import pytest

pytestmark = pytest.mark.macos


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit monitors are macOS-only")
def test_real_appkit_monitors_register_and_release(qapp):
    pytest.importorskip("AppKit")
    from lingoflow.infrastructure.macos.event_monitor import OutsideInteractionMonitor

    class Window:
        def clicked(self):
            pass

        def switched(self):
            pass

    window = Window()
    monitor = OutsideInteractionMonitor()
    monitor.start(window.clicked, window.switched)
    try:
        assert monitor.active_count == 2
    finally:
        monitor.close()
    assert monitor.active_count == 0
