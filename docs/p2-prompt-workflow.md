# P2 — Prompt Engineering Workflow

Owner: P2 (`log_triage/prompt.py`). Goal: a foundational prompt layer that
produces **grounded anomaly JSON**, designed so best-of-N (today) and SFT/ReST
(later) drop in with no rework.

## Ground truth (the team's actual contract — do NOT break these)

- Model: **`gemini-2.0-flash`** via the `google-generativeai` SDK (`config.py`).
  API-only — you cannot train it. (Reinforces: SFT/RLVR = switch to open Gemma
  weights, future work.)
- Output: a **JSON array of anomaly objects per chunk** (`validator.py`,
  `main.py`). Not a single object.
- Required fields per object: `service_name`, `timestamp`, `error_severity`
  (INFO|WARNING|ERROR|**FATAL**), `suggested_remediation`, `source_line`
  (verbatim). `additionalProperties: false` -> **no extra fields allowed**, so
  we cannot add a per-object `reasoning` field without coordinating a schema
  change with P3.
- `source_line` is the grounding anchor already. Good — best-of-N keys off it.

## How best-of-N fits THIS pipeline (array output -> self-consistency)

Because each chunk returns a *set* of anomalies, "sample N, keep the single
best" doesn't apply. The right analogue is **self-consistency voting**:

```
for each chunk:
    candidates = sample_candidates(chunk, n=4, temperature=0.7)   # P2: prompt.py
    events = []
    for raw in candidates:
        for e in extract_and_validate(raw):        # P3: schema-valid only
            if is_grounded(e, chunk):              # source_line IN chunk  <-- key
                events.append(e)
    keep events whose (timestamp, source_line) appears in >= k of N samples
```

Why this is the anti-hallucination mechanism: an invented `source_line` fails
`is_grounded` immediately, and a one-off hallucination rarely repeats across N
samples, so the >=k vote drops it. Real anomalies are stable across samples and
survive. Same reward (`is_grounded`) that a future RLVR run would optimize.

## What P2 delivered in prompt.py

- `call_gemini(chunk, use_fallback, temperature)` — added `temperature` so the
  same wrapper serves deterministic (0.0) and sampled (>0) modes. Back-compat:
  `main.py`'s `call_gemini(chunk, use_fallback=...)` still works.
- `sample_candidates(chunk, n, temperature)` — returns N raw responses. The
  best-of-N entry point. n=1 == old behavior.
- `is_grounded(event, chunk)` — the verbatim `source_line in chunk` check. The
  core reward signal for voting now and RLVR later.

## Phases

### Phase 0 — Foundational (done)
- [x] temperature-aware `call_gemini`
- [x] `sample_candidates` (best-of-N entry point)
- [x] `is_grounded` (grounding reward)
- [ ] smoke test against the API (n=1, temperature=0) on `sample_production_logs.txt`

### Phase 1 — Best-of-N wired in (P3/P4 seam)
- Orchestrator (`main.py`/`process_chunk`) calls `sample_candidates` instead of
  one `call_gemini`, runs the voting loop above. No prompt change needed.
- NOTE: `validator.py` currently checks schema only, NOT grounding. Wire
  `is_grounded` into the keep-filter — this is the highest-leverage
  anti-hallucination change and it's currently missing.

### Phase 2 — Optimize prompt
- Tighten `SYSTEM_PROMPT` noise rules; regression-test on `tests/*.txt`.
- Tune `n` and `temperature` for best grounded-valid yield vs. API cost.

### Phase 3 — SFT-ready handoff (post-hackathon)
- Per chunk, the surviving voted+grounded events are the training target:
  `{"input": <chunk>, "output": <voted event array>}` -> JSONL. Same schema,
  no rework. This is the ReST dataset.

## Honest scoping
- best-of-N + voting = inference-time, no training. Not RL.
- SFT/ReST/RLVR require open Gemma weights (Flash is API-only) -> future work,
  see `docs/rlvr-workflow.md`.
