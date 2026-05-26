from __future__ import annotations


def test_core_modules_import_without_starting_the_app() -> None:
    import lingoflow.app
    import lingoflow.config.settings
    import lingoflow.core.app_state
    import lingoflow.core.ocr
    import lingoflow.core.ports
    import lingoflow.core.translator
    import lingoflow.infrastructure.ollama_client
    import lingoflow.infrastructure.tasks
    import lingoflow.ui.main_window
    import lingoflow.ui.messages
    import lingoflow.ui.ocr_workflow
    import lingoflow.ui.settings_coordinator
    import lingoflow.ui.translation_workflow
    import lingoflow.ui.tray_controller

    assert lingoflow.app.main is not None
