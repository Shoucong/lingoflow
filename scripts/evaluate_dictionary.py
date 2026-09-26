#!/usr/bin/env python3
"""Measure offline dictionary lookups on words typical of reading papers.

Reports, per word, which dictionary answered, the resolved headword, the first
senses and the lookup time. No model is called and nothing leaves the Mac.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

WORDS = {
    "inflection": [
        "inhibited",
        "inhibits",
        "mediates",
        "attenuated",
        "conferred",
        "elucidating",
        "binding",
        "bound",
        "underlying",
        "assays",
        "cleaved",
        "analyses",
        "criteria",
        "phenomena",
        "hypotheses",
        "mice",
        "ran",
        "better",
        "lying",
        "yielded",
    ],
    "academic": [
        "inhibit",
        "mediate",
        "elucidate",
        "robust",
        "putative",
        "ubiquitous",
        "attenuate",
        "confer",
        "whereas",
        "albeit",
        "thereby",
        "notably",
        "respectively",
        "moreover",
        "plausible",
        "novel",
        "abundance",
        "consistent",
        "robustly",
        "discrepancy",
    ],
    "biomedical": [
        "kinase",
        "kinases",
        "apoptosis",
        "phosphorylated",
        "ubiquitination",
        "transcription",
        "transcriptional",
        "promoter",
        "ligand",
        "receptor",
        "antibody",
        "antigen",
        "cytokine",
        "enzyme",
        "mitochondria",
        "mitochondrial",
        "knockdown",
        "upregulated",
        "homolog",
        "plasmid",
        "pathway",
        "phenotype",
        "genotype",
        "allele",
        "mutation",
        "epitope",
        "vaccine",
        "pathogen",
        "inflammation",
        "metabolism",
    ],
    "polysemous": [
        "window",
        "paper",
        "cell",
        "culture",
        "express",
        "expression",
        "yield",
        "significant",
        "model",
        "strain",
        "host",
        "vector",
        "medium",
        "fraction",
        "resolution",
    ],
    "chinese": ["抑制", "结合", "表达"],
}


def summarize(result) -> dict:
    if result is None:
        return {"dictionary": None}
    entries = []
    for entry in result.entries[:3]:
        senses = [
            {
                "part": part.label,
                "domains": list(sense.domains),
                "meaning": "；".join(sense.translations) or sense.definition[:120],
            }
            for part in entry.parts
            for sense in part.senses
        ]
        entries.append(
            {
                "headword": entry.headword,
                "form_of": list(entry.form_of) if entry.form_of else None,
                "pronunciations": [f"{p.dialect} {p.ipa}".strip() for p in entry.pronunciations],
                "sense_count": len(senses),
                "first_senses": senses[:4],
            }
        )
    return {
        "dictionary": result.source_name,
        "bilingual": result.bilingual,
        "found": result.found,
        "entries": entries,
    }


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from lingoflow.infrastructure.macos.dictionary import MacOSDictionaryService

    service = MacOSDictionaryService()
    started = time.perf_counter()
    available = service.available
    load_ms = (time.perf_counter() - started) * 1000
    report = {"available": available, "load_ms": round(load_ms, 2), "words": {}}
    timings = []
    for group, words in WORDS.items():
        for word in words:
            target = "English" if group == "chinese" else "Chinese(Simplified)"
            started = time.perf_counter()
            result = service.lookup(word, target)
            elapsed = (time.perf_counter() - started) * 1000
            timings.append(elapsed)
            report["words"][word] = {"group": group, "ms": round(elapsed, 2), **summarize(result)}
    values = report["words"].values()
    report["summary"] = {
        "words": len(timings),
        "bilingual_found": sum(1 for v in values if v.get("bilingual") and v.get("found")),
        "monolingual_fallback": sum(1 for v in values if v.get("bilingual") is False),
        "nothing": sum(1 for v in values if not v.get("found")),
        "median_ms": round(statistics.median(timings), 2),
        "max_ms": round(max(timings), 2),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    for word, value in report["words"].items():
        first = value.get("entries", [{}])[0] if value.get("entries") else {}
        senses = first.get("first_senses", [])
        meaning = " | ".join(s["meaning"][:28] for s in senses[:3])
        kind = "双语" if value.get("bilingual") else ("英英" if value.get("dictionary") else "无")
        form = f" ({first['form_of'][0]} of {first['form_of'][1]})" if first.get("form_of") else ""
        print(
            f"{word:16} {kind} {value['ms']:6.1f}ms → {first.get('headword', '-')}{form}: {meaning}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
