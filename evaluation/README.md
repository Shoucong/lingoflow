# Translation regression fixtures

`cases.json` contains 30 original synthetic examples, not private reading content.
They cover negation, uncertainty, numbers/units, citations, formulas, code/URLs,
OCR line breaks, paragraphs and a 6,525-character document with 28 numbered values
and a final marker. Keep fixture changes explicit so recorded hashes stay meaningful.

```sh
.venv/bin/python scripts/evaluate_models.py \
  --model huihui_ai/hunyuan-mt-abliterated:7b-chimera \
  --model zongwei/gemma3-translator:4b \
  --legacy-baseline --output build/evaluation.json
.venv/bin/python scripts/check_runtime.py \
  --model huihui_ai/hunyuan-mt-abliterated:7b-chimera \
  --output build/runtime.json
QT_QPA_PLATFORM=cocoa .venv/bin/python scripts/check_cold_start_reopen.py \
  --output build/cold-start-reopen.json
```

Only models already installed on loopback Ollama are used. No model download or
remote inference is performed. The runners construct defaults instead of loading
personal settings. Evaluation retains the synthetic inputs/outputs in its report;
normal application content logging remains disabled by default.

The cold-start/reopen check requires the default model to be absent from `/api/ps`;
it does not unload resident models. It sends synthetic text, waits until the chat
request body has been sent, closes the native popup before any output, and immediately
triggers a second selection. Clipboard capture and the physical global keyboard
event are replaced with a synthetic selection and the same Qt trigger signal.

The legacy profile reproduces the original translation prompt, omitted generation
options, and the selection entry's 5,000-character cap. It uses the new strict
transport parser; it is **not** a timing run of the old application binary.
Residency is recorded before each profile. The first request may include model
loading or context-size reallocation; do not label every first request “cold”.

Literal-preservation checks catch some regressions but are not translation quality
scores. Date localization and full-width punctuation can trigger false positives,
while wording mistakes and changed LaTeX delimiters can escape these checks.
Read the source and output when assessing quality. The 2026-09-26 run uses one pass
per profile on a working Mac, including other validation work; timings are
descriptive, not a controlled performance benchmark.
