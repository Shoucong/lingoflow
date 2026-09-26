# macOS architecture

LingoFlow is a single-session menu bar app. Python/PyQt6 owns the UI; Ollama owns
inference. No Windows backend is maintained.

| Layer | Responsibility |
| --- | --- |
| `core/models.py`, `errors.py`, `ports.py` | Portable data, failure categories and interfaces; no native/Qt/HTTP imports. |
| `core/session.py` | Source, output, request ID, terminal state, timing and completed-segment checkpoint. |
| `core/translator.py`, `text_preparation.py` | Prompt/profile selection, lossless source partitioning, output completeness and resumable segments. Transport is injected. |
| `infrastructure/ollama_client.py`, `async_stream.py` | HTTP, model capability query, strict stream parsing and cancellation that interrupts pending I/O. |
| `infrastructure/macos/` | AX/pasteboard selection, Quartz hotkeys, permissions, screenshot process, Vision, speech and native mouse monitors. Screenshot and recognition have separate owners. |
| `ui/translation_view.py` | Editable source and streaming output; append preserves selection and scroll position. |
| `ui/window_controller.py` | Size, placement, screen bounds, pinning and geometry persistence. |
| `ui/popup.py` | Reading controls, speech actions, presentation state and window dismissal policy. |
| `ui/*_workflow.py`, `main_window.py` | Coordinate tasks, reject late request IDs and assemble services. |

Cancellation invalidates the UI request ID first, then stops owned network/native
operations. A stopped/failed session can retain partial output; only fully
completed segments enter a retry checkpoint. Source, language or profile changes
invalidate that checkpoint. Checkpoints stay in memory; no translation history
is written to disk.

The input budget uses UTF-8 bytes as a conservative approximation, with separate
prompt/output reserves. It is not an exact model tokenizer. Large protected
formula/code/URL spans produce a visible budget error rather than being silently
split. Stream completion detects truncation/protocol failure, not semantic
translation omissions; those need the fixed evaluation fixtures and human review.

The clipboard fallback is bounded and checks pasteboard change counts before
restoring. This is best-effort protection, not a cross-process atomic transaction.
Global mouse callbacks keep weak references to windows, and partial registration
is rolled back. Importing domain code does not configure logging; app startup does.

Regression entry points (temporary app data, no real model invocation):

```sh
.venv/bin/python scripts/run_checks.py
.venv/bin/python scripts/run_checks.py --qt-platform cocoa tests/ui
```

The Cocoa suite uses native Qt windows but disables global event monitoring in
widget tests. It does not substitute for installed-app permissions, interactions
with external PDF/browser apps, multiple physical screens or sleep/wake testing.
