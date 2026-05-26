from __future__ import annotations


def test_side_effect_ports_import_cleanly() -> None:
    from lingoflow.core.ports import (
        ClipboardPort,
        HotkeyBackend,
        LLMProvider,
        Notifier,
        OCRBackend,
        PermissionServicePort,
    )

    assert ClipboardPort is not None
    assert LLMProvider is not None
    assert OCRBackend is not None
    assert HotkeyBackend is not None
    assert PermissionServicePort is not None
    assert Notifier is not None
