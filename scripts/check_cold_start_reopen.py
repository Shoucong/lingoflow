#!/usr/bin/env python3
"""Reproduce close/retrigger on an unloaded local model and real Cocoa windows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import httpx
    from PyQt6.QtWidgets import QApplication

    from lingoflow.config.settings import AppSettings
    from lingoflow.core.app_state import AppState, AppStateTracker
    from lingoflow.core.session import SessionStatus
    from lingoflow.infrastructure.tasks import TaskRunner
    from lingoflow.infrastructure.translation_service import create_translation_service
    from lingoflow.ui.main_window import MainSignals
    from lingoflow.ui.popup import TranslationPopup
    from lingoflow.ui.translation_workflow import TranslationWorkflow

    settings = AppSettings()
    settings.ollama.host = "http://127.0.0.1:11434"
    settings.ui.hide_on_focus_loss = False
    with httpx.Client(base_url=settings.ollama.host, timeout=3, trust_env=False) as api:
        resident = api.get("/api/ps").raise_for_status().json()["models"]
    assert not any(
        item["name"] == settings.ollama.model for item in resident
    ), "Default model is already resident. Run after it unloads; this check does not evict models."

    sent = threading.Event()
    original_client = httpx.AsyncClient

    class ObservedClient(original_client):
        async def send(self, request, *args, **kwargs):
            if request.url.path in {"/api/chat", "/api/generate"}:
                request.extensions["trace"] = self.record_trace
            return await super().send(request, *args, **kwargs)

        async def record_trace(self, event, info):
            if event == "http11.send_request_body.complete":
                sent.set()

    class Clipboard:
        text = "Keep the complete source available while the local model starts loading."

        def get_selected_text(self, cancel_check=None):
            return self.text

    class Notifier:
        def update_status(self, status):
            pass

        def show_notification(self, title, message):
            raise AssertionError(f"Unexpected notification: {title}: {message}")

    httpx.AsyncClient = ObservedClient
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    assert app.platformName() == "cocoa"

    def wait_until(predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, "Timed out waiting for workflow"
            app.processEvents()
            time.sleep(0.005)

    service = create_translation_service(settings)
    runner, state, signals, clipboard = TaskRunner(), AppStateTracker(), MainSignals(), Clipboard()
    with tempfile.TemporaryDirectory(prefix="lingoflow-cold-reopen-") as folder:
        workflow = TranslationWorkflow(
            settings=settings,
            translator=service,
            clipboard=clipboard,
            task_runner=runner,
            app_state=state,
            signals=signals,
            notifier=Notifier(),
            popup_factory=lambda config: TranslationPopup(
                config,
                window_state_path=Path(folder) / "window.json",
            ),
        )
        signals.translate_requested.connect(workflow.translate_selection)
        signals.selection_ready.connect(workflow.on_selection_ready)
        signals.translation_chunk.connect(workflow.on_chunk)
        signals.translation_checkpoint.connect(workflow.on_checkpoint)
        signals.translation_error.connect(workflow.on_error)
        signals.translation_completed.connect(workflow.on_completed)
        signals.translation_finished.connect(workflow.on_finished)
        signals.translation_cleared.connect(workflow.on_cleared)
        try:
            signals.translate_requested.emit()
            wait_until(sent.is_set)
            sent_at = time.monotonic()
            wait_until(lambda: time.monotonic() - sent_at >= 0.3)
            assert workflow.popup.isVisible()
            assert not workflow.session.translated_text
            old_task = workflow.active_task
            closed_at = time.monotonic()
            workflow.popup.close()
            close_seconds = time.monotonic() - closed_at
            assert state.current == AppState.IDLE and workflow.active_task is None
            clipboard.text = "The second translation request should open a new window immediately."
            signals.translate_requested.emit()
            wait_until(lambda: workflow.popup is not None and workflow.popup.isVisible(), 2)
            reopen_seconds = time.monotonic() - closed_at
            wait_until(lambda: not old_task._thread.is_alive(), 2)
            cancelled_worker_seconds = time.monotonic() - closed_at
            wait_until(lambda: workflow.active_task is None, 90)
            assert workflow.session.status == SessionStatus.COMPLETED, workflow.session.error
            assert workflow.session.source_text == clipboard.text
            report = {
                "source_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=root,
                    text=True,
                ).strip(),
                "qt_platform": app.platformName(),
                "model": settings.ollama.model,
                "resident_models_before": resident,
                "close_after_http_body_sent_seconds": 0.3,
                "first_request_output_chars_before_close": 0,
                "close_handler_seconds": close_seconds,
                "close_to_new_popup_seconds": reopen_seconds,
                "cancelled_worker_confirmed_exited_seconds": cancelled_worker_seconds,
                "second_first_text_after_close_seconds": workflow.session.first_text_at - closed_at,
                "second_translation": workflow.session.translated_text,
                "active_requests_after": service.client._streams.active_count,
                "completed": True,
                "scope": (
                    "Real local Ollama and native windows; synthetic clipboard and hotkey signal. "
                    "Physical global key/AX acquisition is not exercised."
                ),
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False))
        finally:
            workflow.shutdown()
            workflow.dismiss_popup("Validation complete")
            runner.shutdown()
            httpx.AsyncClient = original_client
            app.processEvents()


if __name__ == "__main__":
    main()
