#!/usr/bin/env python3
"""Prepare anonymized outputs, then join explicit reviewer scores into an offline report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def validate(raw, suite, fixture_path):
    assert raw.get("completed"), "Evaluation has not completed"
    assert raw["fixture_sha256"] == hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    expected = {case["id"] for case in suite["cases"]}
    assert len(expected) == 50 and len(raw["profiles"]) == 4
    for profile in raw["profiles"]:
        assert len(profile["cases"]) == 50
        assert {row["id"] for row in profile["cases"]} == expected


def prepare(raw, suite, destination):
    assert not (destination / "blind_key.json").exists(), "Do not re-randomize an existing review"
    rng = random.SystemRandom()
    number, key, rows = 0, {}, []
    for case in suite["cases"]:
        outputs = []
        profiles = list(raw["profiles"])
        rng.shuffle(profiles)
        for profile in profiles:
            number += 1
            alias = f"R{number:03d}"
            result = next(result for result in profile["cases"] if result["id"] == case["id"])
            key[alias] = {"profile_id": profile["id"], "case_id": case["id"]}
            outputs.append({"review_id": alias, "text": result["output"], "error": result["error"]})
        rows.append({**case, "outputs": outputs})
    write(destination / "blind_cases.json", rows)
    write(destination / "blind_key.json", key)
    print(f"Prepared {number} anonymous translations; model names are in the separate key file.")


def summarize(raw, suite, key, reviews):
    expected = set(key)
    assert set(reviews) == expected, f"Missing/excess review IDs: {set(reviews) ^ expected}"
    decoded = {}
    for review_id, location in key.items():
        rating = reviews[review_id]
        assert isinstance(rating["score"], int) and 0 <= rating["score"] <= 4
        assert rating["note"].strip()
        decoded[(location["profile_id"], location["case_id"])] = {"review_id": review_id, **rating}
    profiles = []
    for profile in raw["profiles"]:
        results = [
            {**row, "review": decoded[(profile["id"], row["id"])]} for row in profile["cases"]
        ]
        for row in results:
            if not row["completed"]:
                assert row["review"]["score"] == 0, "Incomplete outputs must remain failures"
        groups = {}
        for group, items in [
            ("all", results),
            ("en", [x for x in results if x["source_language"] == "en"]),
            ("ja", [x for x in results if x["source_language"] == "ja"]),
            ("bio", [x for x in results if x["topic"] == "ai_drug_discovery"]),
        ]:
            groups[group] = {
                "count": len(items),
                "mean_score": statistics.mean(x["review"]["score"] for x in items),
                "usable": sum(x["review"]["score"] >= 3 for x in items),
                "substantive_correction": sum(x["review"]["score"] <= 2 for x in items),
                "score_counts": {
                    str(i): sum(x["review"]["score"] == i for x in items) for i in range(5)
                },
            }
        warm = [x for x in results if x["model_resident_before"] and x["completed"]]
        cold = [x for x in results if not x["model_resident_before"]]
        resources = [x["resident_after"] for x in results if x["resident_after"]]
        profiles.append(
            {
                "id": profile["id"],
                "label": profile["label"],
                "model": profile["model"],
                "digest": profile["installed"]["digest"],
                "installed_bytes": profile["installed"]["size"],
                "groups": groups,
                "completed": sum(x["completed"] for x in results),
                "warm_median_ttft_s": statistics.median(x["first_text_seconds"] for x in warm),
                "warm_median_total_s": statistics.median(x["total_seconds"] for x in warm),
                "cold_cases": [
                    {
                        "id": x["id"],
                        "ttft_s": x["first_text_seconds"],
                        "total_s": x["total_seconds"],
                        "load_s": (x["ollama"].get("load_duration") or 0) / 1e9,
                    }
                    for x in cold
                ],
                "ollama_reported_resident_bytes": max(x["size"] for x in resources),
                "results": results,
            }
        )
    return {
        "suite_id": suite["suite_id"],
        "fixture_sha256": raw["fixture_sha256"],
        "review_method": (
            "Assistant reviewed model-name-hidden outputs using predeclared checkpoints. "
            "Not independent certified human MQM; subjective diagnostic scores."
        ),
        "profiles": profiles,
    }


def render(report, suite, path):
    esc = lambda value: html.escape(str(value))  # noqa: E731
    rows = []
    for p in report["profiles"]:
        g = p["groups"]
        rows.append(
            f"<tr><th>{esc(p['label'])}</th><td>{g['en']['mean_score']:.2f}</td>"
            f"<td>{g['ja']['mean_score']:.2f}</td><td>{g['bio']['mean_score']:.2f}</td>"
            f"<td>{g['all']['usable']}/50</td><td>{p['cold_cases'][0]['ttft_s']:.2f}s</td>"
            f"<td>{p['warm_median_ttft_s']:.3f}s</td><td>{p['warm_median_total_s']:.2f}s</td>"
            f"<td>{p['ollama_reported_resident_bytes']/1024**3:.2f} GiB</td></tr>"
        )
    cases = []
    for case in suite["cases"]:
        panels, worst = [], 4
        for profile in report["profiles"]:
            item = next(x for x in profile["results"] if x["id"] == case["id"])
            review = item["review"]
            worst = min(worst, review["score"])
            panels.append(
                f"<article><h3>{esc(profile['label'])} <b class='s{review['score']}'>"
                f"{review['score']}/4</b></h3><pre>{esc(item['output'])}</pre>"
                f"<p class='note'>{esc(review['note'])}</p></article>"
            )
        cases.append(
            f"<section class='case' data-language='{case['source_language']}' "
            f"data-topic='{case['topic']}' data-worst='{worst}'>"
            f"<h2>{case['id']} · {esc(case['category'])} · "
            f"{'AI 药物发现' if case['topic']=='ai_drug_discovery' else '通用阅读'}</h2>"
            f"<pre class='source'>{esc(case['text'])}</pre>"
            f"<details><summary>参考译文与预设检查点</summary><p>{esc(case['reference_zh'])}</p>"
            f"<ul>{''.join('<li>'+esc(x)+'</li>' for x in case['checkpoints'])}</ul></details>"
            f"<div class='outputs'>{''.join(panels)}</div></section>"
        )
    document = (ROOT / "evaluation/translation_report_template.html").read_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        document.replace("__ROWS__", "".join(rows)).replace("__CASES__", "".join(cases))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "render"])
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture_path = ROOT / "evaluation/en_ja_zh_50.json"
    raw, suite = read(args.raw), read(fixture_path)
    validate(raw, suite, fixture_path)
    if args.mode == "prepare":
        prepare(raw, suite, args.review_dir)
    else:
        report = summarize(raw, suite, read(args.review_dir / "blind_key.json"), read(args.ratings))
        write(args.output.with_suffix(".json"), report)
        render(report, suite, args.output.with_suffix(".html"))
        print(
            json.dumps(
                [{k: v for k, v in p.items() if k != "results"} for p in report["profiles"]],
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
