"""Close a real reading window before first output, then immediately translate again."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lingoflow.config.settings import AppSettings
from lingoflow.core.app_state import AppState, AppStateTracker
from lingoflow.core.translation_profiles import MILMMT_MODEL
from lingoflow.core.translator import TranslationService
from lingoflow.infrastructure.ollama_client import create_ollama_client
from lingoflow.infrastructure.tasks import TaskRunner
from lingoflow.ui.main_window import MainSignals
from lingoflow.ui.popup import TranslationPopup
from lingoflow.ui.translation_workflow import TranslationWorkflow


@pytest.mark.parametrize(
    "headers_sent", [False, True], ids=["loading-before-headers", "waiting-first-token"]
)
@pytest.mark.parametrize("model", ["generic-model", MILMMT_MODEL], ids=["chat", "milmmt-raw"])
def test_close_during_cold_start_allows_immediate_reopen(
    qtbot, monkeypatch, tmp_path, headers_sent, model
):
    loading, disconnected, release_old = (threading.Event() for _ in range(3))
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, payload):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def do_GET(self):  # noqa: N802
            self.send_json({"models": []})

        def do_POST(self):  # noqa: N802
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                self.send_json({"capabilities": ["completion"]})
                return
            requests.append(payload)
            if len(requests) == 1:
                if headers_sent:
                    self.send_response(200)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.flush()
                loading.set()
                self.connection.settimeout(3)
                try:
                    if self.rfile.read(1) == b"":
                        disconnected.set()
                except OSError:
                    pass
                # The server's old loading work need not finish for the GUI to reopen.
                release_old.wait(5)
                return
            if model == MILMMT_MODEL:
                assert self.path == "/api/generate" and payload["raw"] is True
                self.send_json({"response": "New request completed", "done": True})
            else:
                assert self.path == "/api/chat"
                self.send_json({"message": {"content": "New request completed"}, "done": True})

        def log_message(self, *_args):
            pass

    class Clipboard:
        text = "First selection"

        def get_selected_text(self, cancel_check=None):
            return self.text

    class Notifier:
        def update_status(self, status):
            pass

        def show_notification(self, title, message):
            pytest.fail(f"Unexpected notification: {title}: {message}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = AppSettings()
    settings.ollama.model = model
    settings.ollama.host = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(TranslationPopup, "_start_outside_click_monitor", lambda self: None)
    popups = []

    def make_popup(settings):
        popup = TranslationPopup(settings, window_state_path=tmp_path / "window.json")
        # These WA_DeleteOnClose windows are explicitly closed in the scenario/finally.
        # Keeping deleted wrappers registered with qtbot would close them a second time.
        popups.append(popup)
        return popup

    service = TranslationService(
        settings, client_factory=create_ollama_client, language_detector=lambda text: "English"
    )
    runner, state, signals, clipboard = TaskRunner(), AppStateTracker(), MainSignals(), Clipboard()
    workflow = TranslationWorkflow(
        settings=settings,
        translator=service,
        clipboard=clipboard,
        task_runner=runner,
        app_state=state,
        signals=signals,
        notifier=Notifier(),
        popup_factory=make_popup,
    )
    signals.translate_requested.connect(workflow.translate_selection)
    signals.selection_ready.connect(workflow.on_selection_ready)
    signals.translation_chunk.connect(workflow.on_chunk)
    signals.translation_checkpoint.connect(workflow.on_checkpoint)
    signals.translation_completed.connect(workflow.on_completed)
    signals.translation_error.connect(workflow.on_error)
    signals.translation_finished.connect(workflow.on_finished)
    signals.translation_cleared.connect(workflow.on_cleared)
    try:
        signals.translate_requested.emit()
        qtbot.waitUntil(loading.is_set, timeout=3000)
        old_task = workflow.active_task
        assert workflow.popup.isVisible()
        assert not workflow.session.translated_text
        workflow.popup.close()
        assert workflow.active_task is None and workflow.popup is None
        assert state.current == AppState.IDLE
        assert old_task.is_cancelled()
        clipboard.text = "Second selection"
        # No sleep or wait for the original model-loading operation to finish.
        signals.translate_requested.emit()
        qtbot.waitUntil(lambda: len(popups) == 2 and popups[1].isVisible(), timeout=1500)
        qtbot.waitUntil(lambda: workflow.active_task is None, timeout=3000)
        qtbot.waitUntil(disconnected.is_set, timeout=1500)
        assert not old_task._thread.is_alive()
        assert not release_old.is_set()
        assert workflow.session.source_text == "Second selection"
        assert popups[1].translation_text.toPlainText() == "New request completed"
        # Also reject any old callbacks already queued when the first window closed.
        signals.translation_chunk.emit(old_task.task_id, "Obsolete result")
        signals.translation_finished.emit(old_task.task_id)
        assert popups[1].isVisible()
        assert popups[1].translation_text.toPlainText() == "New request completed"
        assert service.client._streams.active_count == 0
    finally:
        workflow.shutdown()
        workflow.dismiss_popup("Test cleanup")
        release_old.set()
        server.shutdown()
        server.server_close()
        runner.shutdown()
