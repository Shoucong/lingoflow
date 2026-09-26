from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_domain_imports_without_native_gui_or_transport_dependencies() -> None:
    source = Path(__file__).resolve().parents[2] / "src"
    check = """
import sys
sys.path.insert(0, sys.argv[1])
for name in ['PyQt6', 'objc', 'Vision', 'Cocoa', 'AppKit', 'Quartz', 'httpx']:
    sys.modules[name] = None
import lingoflow.core.ports
import lingoflow.core.models
import lingoflow.core.session
import lingoflow.core.translator
assert not any(name.startswith('lingoflow.infrastructure') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", check, str(source)], check=True, timeout=10)


def test_core_modules_import_without_starting_the_app() -> None:
    import lingoflow.app
    import lingoflow.config.settings
    import lingoflow.core.app_state
    import lingoflow.core.ports
    import lingoflow.core.translator
    import lingoflow.infrastructure.macos.ocr
    import lingoflow.infrastructure.ollama_client
    import lingoflow.infrastructure.tasks
    import lingoflow.ui.main_window
    import lingoflow.ui.messages
    import lingoflow.ui.ocr_workflow
    import lingoflow.ui.settings_coordinator
    import lingoflow.ui.translation_workflow
    import lingoflow.ui.tray_controller

    assert lingoflow.app.main is not None
