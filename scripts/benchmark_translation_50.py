#!/usr/bin/env python3
# ruff: noqa: E402 - direct checkout entrypoint, no application startup.
"""Reproducible local EN/JA -> ZH model comparison with complete stream evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from lingoflow.core.translator import TRANSLATION_SYSTEM_PROMPT

PROFILES = {
    "current_hunyuan": {
        "model": "huihui_ai/hunyuan-mt-abliterated:7b-chimera",
        "label": "Current Hunyuan Chimera 7B · Q4_K_M",
        "source": "https://ollama.com/huihui_ai/hunyuan-mt-abliterated:7b-chimera",
        "endpoint": "/api/chat",
        "options": {"temperature": 0.1},
    },
    "hy_mt2": {
        "model": "hf.co/tencent/Hy-MT2-1.8B-GGUF:Q8_0",
        "label": "Hy-MT2 1.8B · Q8_0",
        "source": "https://huggingface.co/tencent/Hy-MT2-1.8B",
        "template_source": "https://huggingface.co/tencent/Hy-MT2-1.8B/blob/main/chat_template.jinja",
        "endpoint": "/api/generate",
        "options": {
            "temperature": 0.7,
            "top_p": 0.6,
            "top_k": 20,
            "repeat_penalty": 1.05,
            "stop": ["<｜hy_place▁holder▁no▁2｜>", "<｜hy_place▁holder▁no▁8｜>", "<｜hy_User｜>"],
        },
    },
    "milmmt": {
        "model": "hf.co/mradermacher/MiLMMT-46-4B-v1.0-GGUF:Q4_K_M",
        "label": "MiLMMT-46-4B-v1.0 · Q4_K_M",
        "source": "https://github.com/xiaomi-research/gemmax",
        "endpoint": "/api/generate",
        "options": {
            "temperature": 0,
            "top_k": 1,
            "repeat_penalty": 1.0,
            "stop": ["<eos>", "<end_of_turn>"],
        },
    },
    "translategemma": {
        "model": "translategemma:4b",
        "label": "TranslateGemma 4B · Ollama official",
        "source": "https://ollama.com/library/translategemma",
        "endpoint": "/api/chat",
        "options": {"temperature": 0, "repeat_penalty": 1.0},
    },
}


def make_payload(profile_id: str, case: dict) -> dict:
    profile = PROFILES[profile_id]
    language = {"en": "English", "ja": "Japanese"}[case["source_language"]]
    source = case["text"]
    payload = {
        "model": profile["model"],
        "stream": True,
        "keep_alive": 600,
        "options": {"num_ctx": 8192, "num_predict": 4096, "seed": 42, **profile["options"]},
    }
    if profile_id == "current_hunyuan":
        # Reproduce the actual app baseline, whose source language is configured as auto.
        payload["messages"] = [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Translate the following text to Chinese(Simplified):\n\n" + source,
            },
        ]
    elif profile_id == "hy_mt2":
        instruction = (
            "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n" + source
        )
        payload.update(
            raw=True,
            prompt=("<｜hy_begin▁of▁sentence｜><｜hy_User｜>" + instruction + "<｜hy_Assistant｜>"),
        )
    elif profile_id == "milmmt":
        payload.update(
            raw=True,
            prompt=(
                f"Translate this from {language} to Chinese (Simplified):\n"
                f"{language}: {source}\nChinese (Simplified):"
            ),
        )
    else:
        prompt = (
            f"You are a professional {language} ({case['source_language']}) to Chinese (zh-Hans) "
            "translator. Your goal is to accurately convey the meaning and nuances of the "
            f"original {language} text while adhering to Chinese grammar, vocabulary, and "
            "cultural sensitivities.\nProduce only the Chinese translation, without any "
            "additional explanations or commentary. Please translate the following "
            f"{language} text into Chinese:\n\n\n{source}"
        )
        payload["messages"] = [{"role": "user", "content": prompt}]
    return payload


def infer(api: httpx.Client, profile_id: str, case: dict) -> dict:
    payload = make_payload(profile_id, case)
    started = time.perf_counter()
    first, done, error, final = None, False, None, {}
    chunks = []
    try:
        with api.stream("POST", PROFILES[profile_id]["endpoint"], json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                frame = json.loads(line)
                if not isinstance(frame, dict) or frame.get("error"):
                    raise ValueError(f"Invalid/error frame: {frame}")
                content = (
                    frame.get("response", "")
                    if "prompt" in payload
                    else frame.get("message", {}).get("content", "")
                )
                if not isinstance(content, str):
                    raise ValueError("Non-text output")
                if content.strip() and first is None:
                    first = time.perf_counter() - started
                chunks.append(content)
                if frame.get("done") is True:
                    done, final = True, frame
                    if frame.get("done_reason") not in {None, "stop"}:
                        raise ValueError(f"Incomplete generation: {frame.get('done_reason')}")
                    break
        if not done:
            raise ValueError("Stream ended without a completion frame")
        if not "".join(chunks).strip():
            raise ValueError("Empty translation")
    except Exception as failure:
        error = f"{type(failure).__name__}: {failure}"
    elapsed = time.perf_counter() - started
    text = "".join(chunks)
    return {
        "id": case["id"],
        "source_language": case["source_language"],
        "category": case.get("category"),
        "topic": case.get("topic"),
        "source_chars": len(case["text"]),
        "payload": payload,
        "output": text,
        "first_text_seconds": first,
        "total_seconds": elapsed,
        "completed": done and error is None,
        "error": error,
        "ollama": {
            key: final.get(key)
            for key in [
                "done_reason",
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            ]
        },
        "literal_flags": [value for value in case.get("literal_checks", []) if value not in text],
    }


def save_json(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    fixture_path = ROOT / "evaluation/en_ja_zh_50.json"
    suite = json.loads(fixture_path.read_text())
    cases = sorted(suite["cases"], key=lambda case: (int(case["id"][1:]), case["id"][0]))
    assert len(cases) == 50 and len({case["id"] for case in cases}) == 50
    if args.smoke:
        cases = [
            {
                "id": "smoke-en",
                "source_language": "en",
                "text": "The test did not fail. The value was 12.5.",
            },
            {
                "id": "smoke-ja",
                "source_language": "ja",
                "text": "この結果は、成功を保証するものではありません。",
            },
        ]
    record = {
        "suite": suite["suite_id"],
        "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": (
            "Preflight outside scored suite"
            if args.smoke
            else "50 identical diagnostic inputs per model, no silent retries"
        ),
        "profiles": [],
    }
    assert not args.output.exists(), "Use a new output path; do not overwrite an existing run"
    timeout = httpx.Timeout(connect=10, read=180, write=30, pool=10)
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=timeout) as api:
        record["ollama_version"] = api.get("/api/version").raise_for_status().json()
        installed = {
            model["name"]: model
            for model in api.get("/api/tags").raise_for_status().json()["models"]
        }
        owned = {p["model"] for p in PROFILES.values()}
        for profile_id, config in PROFILES.items():
            resident = api.get("/api/ps").raise_for_status().json()["models"]
            other = [m["name"] for m in resident if m["name"] not in owned]
            assert not other, f"Another model is resident; avoid altering its state: {other}"
            for model in resident:
                api.post(
                    "/api/generate", json={"model": model["name"], "keep_alive": 0}
                ).raise_for_status()
            show = api.post("/api/show", json={"model": config["model"]}).raise_for_status().json()
            profile = {
                "id": profile_id,
                **config,
                "installed": installed[config["model"]],
                "imported_template": show.get("template"),
                "imported_parameters": show.get("parameters"),
                "model_info": show.get("model_info"),
                "cases": [],
            }
            record["profiles"].append(profile)
            save_json(args.output, record)
            try:
                for index, case in enumerate(cases):
                    before = api.get("/api/ps").raise_for_status().json()["models"]
                    result = infer(api, profile_id, case)
                    result["model_resident_before"] = any(
                        item["name"] == config["model"] for item in before
                    )
                    profile["cases"].append(result)
                    residents = api.get("/api/ps").raise_for_status().json()["models"]
                    result["resident_after"] = next(
                        (item for item in residents if item["name"] == config["model"]), None
                    )
                    save_json(args.output, record)
                    print(
                        f"{profile_id} {case['id']} {result['total_seconds']:.2f}s "
                        f"{result['error'] or 'complete'}"
                        + (f" {result['output']!r}" if args.smoke else ""),
                        flush=True,
                    )
            finally:
                api.post(
                    "/api/generate", json={"model": config["model"], "keep_alive": 0}
                ).raise_for_status()
        record["completed"] = True
        save_json(args.output, record)


if __name__ == "__main__":
    main()
