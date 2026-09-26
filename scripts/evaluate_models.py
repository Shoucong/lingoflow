#!/usr/bin/env python3
# ruff: noqa: E402 - allow direct execution from an uninstalled checkout.
"""Evaluate explicit, synthetic fixtures against models already installed locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from lingoflow.config.settings import AppSettings
from lingoflow.core.translator import TRANSLATION_SYSTEM_PROMPT
from lingoflow.infrastructure.translation_service import create_translation_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/cases.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-baseline", action="store_true")
    args = parser.parse_args()
    if urlparse(args.host).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This runner is restricted to local Ollama.")
    cases = json.loads(args.cases.read_text())
    with httpx.Client(base_url=args.host, trust_env=False, timeout=10) as api:
        installed = api.get("/api/tags").raise_for_status().json()["models"]
        known = {item["name"]: item for item in installed}
        for model in args.model:
            if model not in known:
                parser.error(f"Model not installed: {model}")
        record = {
            "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "ollama": api.get("/api/version").raise_for_status().json(),
            "fixture_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
            "scope": (
                "Synthetic fixtures, local inference only. "
                "Literal checks are not semantic quality scores."
            ),
            "profiles": [],
        }
        profiles = [(model, "current") for model in args.model]
        if args.legacy_baseline:
            profiles.insert(0, (args.model[0], "legacy-selection-profile"))
        args.output.parent.mkdir(parents=True, exist_ok=True)

        def save():
            temporary = args.output.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(args.output)

        for model, mode in profiles:
            settings = AppSettings()
            settings.ollama.host = args.host
            settings.ollama.model = model
            service = create_translation_service(settings)
            profile = {
                "model": known[model],
                "mode": mode,
                "settings": settings.ollama.model_dump() if mode == "current" else None,
                "resident_before": api.get("/api/ps").raise_for_status().json(),
                "note": (
                    "Legacy prompt, no generation options, selection capped at 5000 chars; "
                    "uses current strict transport parser, not an old application binary."
                    if mode != "current"
                    else "Current application service; faithful preset."
                ),
                "cases": [],
            }
            record["profiles"].append(profile)
            save()
            for case in cases:
                source = case["text"]
                submitted = source if mode == "current" else source[:5000]
                parts, checkpoints, first, error = [], [], None, None
                started = time.perf_counter()
                try:
                    if mode == "current":
                        stream = service.translate_stream(
                            submitted, on_checkpoint=checkpoints.append
                        )
                    else:
                        stream = (
                            chunk.content
                            for chunk in service.client.chat_stream(
                                message=(
                                    "Translate the following text to Chinese(Simplified):\n\n"
                                    + submitted
                                ),
                                model=model,
                                system_prompt=TRANSLATION_SYSTEM_PROMPT,
                            )
                        )
                    for chunk in stream:
                        if chunk and first is None:
                            first = time.perf_counter() - started
                        parts.append(chunk)
                except Exception as failure:
                    error = str(failure)
                output = "".join(parts)
                profile["cases"].append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "input_chars": len(source),
                        "submitted_chars": len(submitted),
                        "input_complete": source == submitted,
                        "first_text_seconds": first,
                        "total_seconds": time.perf_counter() - started,
                        "completed_parts": len(checkpoints[-1].completed) if checkpoints else None,
                        "total_parts": checkpoints[-1].total if checkpoints else None,
                        "error": error,
                        "output": output,
                        "missing_literals": [
                            word for word in case.get("must_preserve", []) if word not in output
                        ],
                    }
                )
                save()
                print(
                    f"{mode} {model} {case['id']}: {time.perf_counter()-started:.1f}s "
                    f"{'ERROR: ' + error if error else 'completed'}",
                    flush=True,
                )
            service.cancel()
        record["completed"] = True
        save()


if __name__ == "__main__":
    main()
