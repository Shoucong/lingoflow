#!/usr/bin/env python3
# ruff: noqa: E402 - direct execution from a checkout.
"""Check real local Ollama cancellation and bounded worker retention with synthetic text."""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lingoflow.config.settings import AppSettings
from lingoflow.core.errors import TranslationCancelledError
from lingoflow.infrastructure.tasks import TaskRunner
from lingoflow.infrastructure.translation_service import create_translation_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = AppSettings()
    settings.ollama.host = "http://127.0.0.1:11434"
    settings.ollama.model = args.model
    service = create_translation_service(settings)
    source = json.loads((ROOT / "evaluation/cases.json").read_text())[-1]["text"]
    evidence = {"model": args.model, "cancellation": []}
    baseline_threads = threading.active_count()
    for phase in ("before_first_text", "during_stream"):
        cancel, first = threading.Event(), threading.Event()
        parts, errors = [], []

        def generate():
            try:
                for chunk in service.translate_stream(source, cancel_check=cancel.is_set):
                    parts.append(chunk)
                    first.set()
            except TranslationCancelledError:
                pass
            except Exception as error:
                errors.append(str(error))

        worker = threading.Thread(target=generate, name="validation-generation")
        worker.start()
        try:
            deadline = time.monotonic() + 10
            while service.client._streams.active_count == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert service.client._streams.active_count == 1, errors
            if phase == "during_stream":
                assert first.wait(60), errors
            else:
                assert not first.is_set(), "First token arrived before cancellation was tested"
            started = time.monotonic()
            cancel.set()
            service.cancel()
            worker.join(2)
            assert not worker.is_alive(), "Cancelled HTTP request did not exit promptly"
            assert not errors, errors
            assert service.client._streams.active_count == 0
            evidence["cancellation"].append(
                {
                    "phase": phase,
                    "seconds": time.monotonic() - started,
                    "partial_chars": len("".join(parts)),
                    "active_requests_after": service.client._streams.active_count,
                }
            )
        finally:
            cancel.set()
            service.cancel()
            worker.join(3)
    recovered = service.translate("The window can be resized.")
    assert recovered.status.value == "completed", recovered.error_message
    evidence["recovery_translation"] = recovered.translated_text
    runner = TaskRunner()
    for _ in range(250):
        task = runner.start("lifecycle-check", lambda task: None)
        task._thread.join(1)
    runner.shutdown()
    assert runner.active_count == 0 and len(runner.recent) == 100
    evidence["tasks_exercised"] = 250
    evidence["retained_active_tasks"] = runner.active_count
    evidence["retained_diagnostics"] = len(runner.recent)
    evidence["python_threads_before"] = baseline_threads
    evidence["python_threads_after"] = threading.active_count()
    evidence["completed"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
