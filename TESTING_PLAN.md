# LingoFlow Testing Plan

This plan replaces the old manual development scripts under `tests/`.

The goal is to build a real pytest-based suite that catches regressions without
requiring Ollama, macOS permission prompts, screen selection, or manual input by
default. Manual end-to-end checks still matter for a macOS menu bar app, but
they should live outside automated test collection.

## Current Progress

### Applied: Foundation and P0 Regression Slice

- Added pytest configuration and shared isolated-path fixtures.
- Added unit tests for settings validation, backup recovery, task lifecycle,
  mocked Ollama transport behavior, translator prompt/result behavior, and OCR
  capture cleanup.
- Added lightweight UI smoke tests for Settings and popup behavior.
- Added integration checks for app imports and packaging metadata.
- Added `manual_tests/README.md` for release checks that require the signed app,
  user permissions, or real screen capture.

### Applied: MainController Workflow Slice

- Added fake-service workflow tests for selected-text translation.
- Covered Ollama-unavailable and no-selection user notifications.
- Covered long-selection truncation before translation.
- Covered OCR success, cancelled capture, capture errors, and empty OCR results.
- Covered translation error display in the popup.
- Covered popup-close cancellation of active translation work.
- Covered settings propagation to translator, OCR, hotkeys, and popup.
- Covered stale translation signal suppression.

Validation command:

```bash
.venv/bin/python -m pytest
```

Current result: 52 passing tests.

## Test Strategy

Use three layers:

1. Unit tests
   - Fast.
   - No real Ollama.
   - No real macOS permissions.
   - No real screen capture.
   - No real pasteboard mutation.

2. Component tests
   - Qt widgets with `pytest-qt`.
   - Fake services and signal assertions.
   - No real tray icon requirement where avoidable.

3. Manual release checks
   - Run from the built `.app` and `.dmg`.
   - Validate permissions, menu bar behavior, hotkeys, OCR selection, and update flow.

## Proposed Test Layout

```text
tests/
  conftest.py
  unit/
    test_settings.py
    test_ollama_client.py
    test_translator.py
    test_hotkey_parser.py
    test_task_runner.py
    test_ocr_service.py
  ui/
    test_settings_dialog.py
    test_popup.py
    test_main_controller_workflows.py
  integration/
    test_app_imports.py
    test_packaging_metadata.py
manual_tests/
  README.md
```

Manual tests should be opt-in scripts or checklists only. They should not be
named so pytest collects them by accident.

## Test Infrastructure

Add pytest configuration:

- Use `QT_QPA_PLATFORM=offscreen` for widget tests where possible.
- Mark tests that require macOS APIs with `@pytest.mark.macos`.
- Mark tests that require a real Ollama process with `@pytest.mark.ollama`.
- Mark tests that require real user permissions or screen capture with `@pytest.mark.manual`.
- Keep default `pytest` runnable without network, Ollama, or user input.

Recommended default command:

```bash
python -m pytest
```

Recommended local quality command:

```bash
python -m compileall -q src tests scripts
python -m ruff check .
python -m black --check .
python -m mypy src
python -m pytest
```

## Unit Tests

### Settings

Cover:

- Defaults load correctly.
- Legacy config migration chooses the new native macOS path.
- Invalid JSON falls back to backup, then defaults.
- Save is atomic.
- Previous valid config is backed up.
- Ollama host validation rejects missing scheme.
- Empty model names are rejected.
- Source/target languages are validated.
- OCR language is validated.
- Theme is validated.
- Hotkey syntax is validated.
- Translate and OCR hotkeys cannot be identical.
- Privacy defaults keep content logging and OCR capture retention off.

### Ollama Client

Use `httpx.MockTransport` or dependency injection around the HTTP client.

Cover:

- `is_available()` true and false.
- `list_models()` success.
- `chat()` success.
- `chat_stream()` yields chunks.
- Streaming cancellation stops iteration.
- Connect errors map to `OllamaConnectionError`.
- Timeouts map to `OllamaTimeoutError`.
- 404 model errors map to `OllamaModelError`.
- Other HTTP errors map to `OllamaError`.
- Malformed JSON maps to a clean app-level error or is skipped where intended.
- Logs do not include prompt or generated text content.

### Translator

Use a fake Ollama client.

Cover:

- Auto-source prompt construction.
- Explicit-source prompt construction.
- Custom system prompt.
- Streaming chunks are yielded in order.
- `translate()` aggregates chunks.
- Cancellation stops streaming.
- Word lookup logging respects privacy settings.
- Settings updates replace the Ollama client host/model.

### Hotkey Parser

Cover:

- Valid default hotkeys parse.
- Command/Shift/Control combinations parse.
- Missing modifier is rejected.
- Missing key is rejected.
- Unknown key is rejected.
- Multiple non-modifier keys are rejected.
- Display formatting is stable.

### Task Runner

Cover:

- Tasks receive unique ids.
- Task state moves pending -> running -> completed.
- Cancel before start marks cancelled.
- Cancel during work sets cancellation event.
- Failed task records failed state.
- `cancel_all()` cancels all tracked tasks.

### OCR Service

Mock `screencapture` and Apple Vision boundaries.

Cover:

- Unique capture paths are created in the managed cache directory.
- Capture directory permissions are attempted.
- Capture file permissions are attempted.
- Managed capture files are deleted by default.
- Capture files are retained when troubleshooting retention is enabled.
- Unmanaged paths are never deleted.
- Stale captures are cleaned on startup when retention is off.
- Language mapping returns expected Apple Vision identifiers.
- Permission-related screencapture errors produce actionable messages.
- OCR logs avoid exact capture paths in normal messages.

## UI Tests

### Settings Dialog

Use `pytest-qt`.

Cover:

- Dialog is modeless.
- Current settings load into controls.
- Valid settings save and emit `settings_changed`.
- Invalid host prevents save.
- Invalid hotkey prevents save.
- Duplicate hotkeys prevent save.
- Test Connection runs through a background task and updates status.
- Refresh Models runs through a background task and updates the model combo.
- Closing the dialog cancels outstanding settings network tasks.

### Translation Popup

Cover:

- Shows source text and target language.
- Programmatic target-language update does not emit language-change signal.
- User target-language change emits signal.
- Chunks append in order.
- Finish enables copy and clears status later.
- Error state renders without crashing.
- Close emits `closed` exactly once.
- Outside-click/focus-loss behavior can be unit-tested where Qt allows.

### Main Controller Workflows

Use fakes for translator, OCR, clipboard, hotkeys, and notifications.

Cover:

- Translate request with no selected text shows notification.
- Translate request with selected text starts one translation task.
- Repeated translate while active is ignored.
- Popup close cancels active translation task.
- Target-language change cancels old task and starts a new task.
- Stale chunks/errors/finish signals from old task are ignored.
- OCR request starts capture and OCR task.
- OCR failure resets status and shows notification.
- OCR success starts translation.
- Opening Settings does not block popup interaction.
- Quitting cancels active translation and OCR tasks.

## Integration Tests

Keep these lightweight and non-interactive.

Cover:

- All modules import.
- `lingoflow.app.check_dependencies()` can be called with platform/macOS dependencies mocked.
- Bundle metadata source values are stable: bundle id, app name, version, `LSUIElement`.
- Packaging scripts pass shell syntax checks.
- The private project plan stays gitignored.

## Manual Release Checklist

Keep a manual checklist in `manual_tests/README.md` once the automated suite exists.

Manual checks should include:

- Install from DMG into `/Applications`.
- Confirm no Dock icon.
- Confirm single-instance behavior.
- Confirm permissions attach to `LingoFlow.app`.
- Confirm Option+D selected-text translation.
- Confirm Option+S OCR translation.
- Confirm Settings can remain open while popup close button works.
- Confirm Ollama stopped gives a clean failure.
- Confirm invalid settings are rejected.
- Confirm OCR cache is empty after normal OCR.
- Confirm logs do not contain selected/OCR text or exact temporary capture paths.
- Confirm replacing the app preserves permissions with the same signing identity.

## First Implementation Milestone

Build the foundation in this order:

1. Add pytest config and `tests/conftest.py`.
2. Add unit tests for settings validation and atomic save.
3. Add unit tests for `TaskRunner`.
4. Add unit tests for `OllamaClient` error mapping with mocked transport.
5. Add translator prompt/cancellation tests with a fake client.
6. Add OCR cache cleanup tests with temporary paths.
7. Add Settings dialog and popup smoke tests with `pytest-qt`.
8. Add MainController workflow tests with fake services.

This gives LingoFlow a stable safety net before the next architecture cleanup.
