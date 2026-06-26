# Harder Path: RL-meets-NTP for Log Triage

The goal of this track is to attack the two real pain points of base Gemma on
log triage — **hallucination** (citing service names / timestamps that aren't
in the log) and **token limits** (rambling chain-of-thought eats the output
budget before clean JSON appears) — using the "RL meets next-token-prediction"
idea: keep the model's next-token objective, but shape it with a **verifiable
reward**.

This is *future work* for the 2.5h hackathon. But its core component — the
reward/verifier — is something we build and demo TODAY, at inference time.

---

## 0. Why this task is a textbook RLVR fit

RLVR (RL with Verifiable Rewards) works when you can score an output
**mechanically, with no human and no learned reward model**. Log triage gives
us exactly that. Given a log `L` and a candidate JSON `y`, the reward is:

```
r(L, y) =  w1 * json_parses(y)              # 0/1  — valid JSON object
         + w2 * has_required_keys(y)        # 0/1  — service_name, timestamp,
                                            #        error_severity, suggested_remediation
         + w3 * grounded(y, L)              # 0/1  — the cited timestamp AND
                                            #        service_name appear verbatim in L
         + w4 * severity_correct(y, gold)   # 0/1  — only if we have a gold label
```

`w3` (grounding) is the anti-hallucination term and the most important one: a
model that invents a line that isn't in `L` gets penalized every time. This
reward is `log_triage/validator.py` + `log_triage/scorer.py` — the same code
the live pipeline uses to gate output. **One artifact, three jobs: runtime
gate, eval metric, RL reward.**

---

## 1. Inference-time version (DEMO THIS in 2.5h)

We do not need to train to show the reward working. Use **best-of-N +
verifier reranking** (a.k.a. rejection sampling):

```
for each log chunk L:
    samples = [ model(L) for _ in range(N) ]   # N=4, temperature ~0.7
    best    = argmax_{y in samples} r(L, y)     # score with validator/scorer
    if r(L, best) < threshold:
        repair_or_flag(best)                    # JSON-repair pass, or mark low-confidence
    emit best
```

Why this matters: **best-of-N + verifier reranking is the greedy, test-time
shadow of what RLVR bakes into the weights.** RLVR would train the policy so
that high-reward completions become the *most likely* next-token sequences;
best-of-N just samples a few and keeps the best one now. Same reward, same
objective — one is amortized into weights, one is paid at inference.

Demo slide: base (single greedy sample) vs. best-of-4 + verifier. Expect
hallucination rate down and JSON-valid rate up with zero training.

---

## 2. Training-time version (the real RLVR pipeline — post-hackathon)

Run only if a subset of the team has GPU access (≥48GB for a useful Gemma
size; iterate on a 4B–12B Gemma, not 31B).

### Stage A — Build the reward (done already, see §0)
`validator.py` + `scorer.py`. This is the gate for *everything* downstream.

### Stage B — Data via distillation ("front-loading reasoning data")
1. Take the corpus of raw logs.
2. Use a strong teacher model to produce `reasoning + JSON` for each.
3. **Filter through the reward**: keep only traces where `r >= threshold`.
4. Result: clean `(log -> short reasoning -> grounded JSON)` SFT set, with no
   hand-labeling.

### Stage C — SFT (LoRA / QLoRA)
Teach Gemma the *shape*: reason briefly, cite the offending line verbatim,
then emit JSON. This removes the need for the giant instruction prompt and the
`{`-prefill hack, and gives the model "direction." Output format trains the
"reason then answer" behavior — the accessible analogue of front-loading
reasoning.

### Stage D — RLVR (GRPO)
- For each log, sample G completions from the SFT policy.
- Score each with the reward from §0.
- GRPO updates the policy toward the above-average-reward completions
  (group-relative advantage), still optimizing next-token likelihood.
- This is the step that *durably* crushes hallucination: ungrounded outputs
  are systematically down-weighted in the weights, not just filtered at
  inference.

### Stage E — Re-eval
Same before/after table as §1, now: base vs. SFT vs. SFT+RLVR, scored by the
§0 reward on a held-out log set.

---

## 3. How this answers the two pain points

| Pain point | Inference-time fix (today) | Training-time fix (RLVR) |
|---|---|---|
| **Hallucination** | grounding term `w3` + best-of-N rerank rejects ungrounded samples | GRPO down-weights ungrounded completions in the weights |
| **Token limit** | chunk the log (map-reduce); `responseSchema` stops rambling CoT; short bounded reasoning field | SFT trains short reasoning -> JSON, so less budget wasted on markdown thinking |

---

## 4. Honest scoping note for the writeup

- This is **not** RLP. RLP is an RL *pretraining* objective requiring
  pretraining-scale infra we do not have. The defensible claim is:
  *"the talk's reasoning-front-loading and RL-over-next-token-prediction ideas
  inspired an SFT -> RLVR pipeline on open Gemma weights, with a programmatic
  verifiable reward; we demo the reward at inference via best-of-N reranking
  and outline the GRPO training extension."*
- Do not claim a trained RLVR model unless Stage D actually ran and Stage E
  shows the numbers.
