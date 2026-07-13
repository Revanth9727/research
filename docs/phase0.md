# Phase 0 — Detailed Build Plan

## Two-Week Go/No-Go: Multi-Agent Retention Localization

*Working notes, July 2026*

---

## What Phase 0 Is

A minimal kill-check. We build a 3-agent synthetic QA pipeline, inject typed faults, and ask one question: **does a drop in retention score reliably point to the agent that caused it?**

Two sub-stages:
- **v0a (detection):** faults only at Agent 2. Primary signal is the **paired comparison** R(m2_clean) vs R(m2_faulted) — same message position, clean run vs faulted run. This isolates the fault's effect from any pipeline noise. The retention curve is *not* the primary v0a signal.
- **v0b (localization):** faults at Agent 1, 2, or 3. Does the largest drop in the retention curve point to the right handoff? This is the real test — fault location must vary for localization to be meaningful.

If both pass all gate criteria, we commit to Phase 1. If not, we stop here.

---

## Architecture

### The 3-Agent Pipeline

```
Evidence + Question
        │
        ▼
  ┌─────────────┐     message m1     ┌─────────────┐     message m2     ┌─────────────┐
  │  Agent 1    │ ─────────────────► │  Agent 2    │ ─────────────────► │  Agent 3    │
  │  Retriever  │                    │  Reasoner   │                    │  Answerer   │
  └─────────────┘                    └─────────────┘                    └─────────────┘
                                                                                │
                                                                         final answer
```

**Fault injection** is applied at the handoff *before* the next agent receives the message:
- `fault_agent: 1` → inject into m1 before Agent 2 sees it
- `fault_agent: 2` → inject into m2 before Agent 3 sees it
- `fault_agent: 3` → inject into Agent 3's final output

**v0a primary signal:** R(m2_clean) vs R(m2_faulted) — the same handoff scored on a clean run and a faulted run. A paired comparison that isolates the fault; it is not a curve.

**v0b signal — retention curve** computed over the original evidence plus every message:

```
R(evidence) → R(m1) → R(m2) → R(final)
```

The handoff with the largest single-step drop is the predicted fault location. The curve only becomes meaningful in v0b where fault location varies.

### Agent Roles and Message Format

Each agent outputs structured JSON:

```json
{
  "known_facts": [],
  "reasoning_summary": "",
  "answer_candidate": ""
}
```

- **Retriever (Agent 1):** given evidence + question, selects relevant facts and populates `known_facts`.
- **Reasoner (Agent 2):** given m1, chains facts toward the answer, fills `reasoning_summary` and `answer_candidate`.
- **Answerer (Agent 3):** given m2, produces the final answer string.

### Retention Scoring

A **frozen reader model** is given a message and asked to answer the question from that message alone. It returns a raw string (or `UNKNOWN`). A separate `scoring.py` converts that string to 1/0 against a target answer.

Two scores are tracked:
- `R_correct` — can the gold answer be recovered from this message?
- `R_corrupt` — can the corrupted answer be recovered? (corruption rows only)

**Majority vote:** each message is scored with three prompt phrasings. `R = 1` if at least 2 of 3 prompts recover the target. The raw rate (e.g. 2/3) is logged as `reader_stability`.

**Leakage controls (v0a only):** each example is also scored at `no_context` (empty message) and `irrelevant_context` (unrelated example's facts). If `R_correct(no_context) = 1`, set `memory_leak_flag = 1` — the example is contaminated and excluded. For fabricated-fact examples, `no_context` recovery should almost always be 0; the controls exist to prove that.

**v0 scoring:** binary exact match after normalization (lowercase, strip punctuation/whitespace; numbers and units preserved so `"80 years"` ≠ `"45 years"`). Logprob upgrade is later.

**Distinguishing fault types by signal:**

| Fault type          | R_correct | R_corrupt | Signal                                |
|---------------------|-----------|-----------|---------------------------------------|
| Benign compression  | stable    | —         | No drop → not a fault                 |
| Destructive deletion| drops     | stable    | Drop with no rise in R_corrupt        |
| Corruption          | drops     | rises     | Drop in R_correct + rise in R_corrupt |
| Re-derivation       | drops then recovers | — | Non-monotonic pattern              |

### Model Stack

- **Agents (v0a):** deterministic templated functions — no live API calls. Agent 1 passes all evidence into `known_facts`; Agent 2 passes them through; Agent 3 reads from the message. No generation noise, so a failed run cannot be blamed on model variability. Hosted agents (GPT-4o-mini or equivalent) are added only after the signal is confirmed in v0a.
- **Reader:** Frozen open-weight model — Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct via local inference or a separate API call. Must be held fixed across all runs. `reader.py` takes a message and question, prompts the frozen reader, and returns the raw answer string.
- **Scoring:** `scoring.py` compares the raw reader output against a target answer and returns 1 or 0. Target is always explicit — never hardcoded to gold — so corruption can be scored against both the gold and the corrupted answer. Binary exact match (v0); logprob upgrade is later.

---

## Pass / Fail Gate

### v0a Gate

v0a passes only if all hold across the 20 examples:
- Clean: `R_correct_clean = 1` and `R_correct_faulted = 1`.
- Benign compression: `R_correct_clean = 1` and `R_correct_faulted = 1`.
- Destructive deletion: `R_correct_clean = 1` and `R_correct_faulted = 0`.
- Corruption: `R_correct_clean = 1`, `R_correct_faulted = 0`, and `R_corrupt_faulted = 1`.
- No examples used for the main result have `memory_leak_flag = 1`.

If v0a fails, stop. Do not proceed to v0b.

### v0b Gate

All five must hold:

1. Retention-drop method beats **random** localization.
2. Beats **blame-last** (always accuse the last agent).
3. Beats **blame-shortest-message** and **blame-longest-message** heuristics.
4. **Benign compression** is not falsely flagged more than ~20% of the time.
5. **Drop-then-recovery** (re-derivation) is detected as a pattern, not treated as a plain failure.

Bonus signal to track: deletion vs. corruption are distinguishable by the `R_corrupt` signal.

---

## File Structure

```
Research/
├── fault_examples_v0a.jsonl      ← EXISTS (v0a only, 20 examples)
├── implementation_plan.md        ← EXISTS
├── plan.md                       ← EXISTS
├── prospectus.md                 ← EXISTS
├── prototype_spec.md             ← EXISTS
├── phase0.md                     ← THIS FILE
│
├── schemas.py                    ← EXISTS: validates every example field
├── load_data.py                  ← EXISTS: reads JSONL + runs validation
│
├── build_messages.py             ← MISSING: deterministic message builder (v0a)
├── inject_faults.py              ← MISSING: applies one fault to Agent 2 message
├── reader.py                     ← MISSING: frozen reader, returns raw answer string
├── scoring.py                    ← MISSING: score_answer(reader_output, target) → 1/0
├── retention.py                  ← MISSING: assembles retention curve + detects drop
├── baselines.py                  ← MISSING: random, blame-last, longest, shortest
├── run_v0a.py                    ← MISSING: detection experiment end-to-end
├── run_v0b.py                    ← MISSING: localization experiment (v0b, later)
├── analyze_results.py            ← MISSING: CSV → summary tables + failure list
├── results/                      ← MISSING: directory for run outputs
│   ├── results_v0a.csv           ← MISSING (written by run_v0a.py)
│   ├── traces_v0a.jsonl          ← MISSING (written by run_v0a.py)
│   └── run_manifest_v0a_<run_id>.json  ← MISSING (written by run_v0a.py before each run)
│
├── data/
│   └── v0b_examples.jsonl        ← MISSING: faults at agents 1 and 3 (v0b only)
│
├── experiment_log.md             ← MISSING: per-run log
└── requirements.txt              ← MISSING
```

---

## What We Have

### `fault_examples_v0a.jsonl` — 20 examples, v0a only

All 20 have `fault_agent: 2`. `expected_fault_handoff` is `"none"` for clean/benign_compression, `"agent2_to_agent3"` for deletion/corruption.

| Fault type           | Count | IDs        | expected_fault_handoff |
|----------------------|-------|------------|------------------------|
| clean                | 5     | ex_001–005 | none                   |
| benign_compression   | 5     | ex_006–010 | none                   |
| destructive_deletion | 5     | ex_011–015 | agent2_to_agent3       |
| corruption           | 5     | ex_016–020 | agent2_to_agent3       |

Schema fields: `id`, `evidence`, `question`, `answer`, `corrupted_answer`, `needed_facts`, `irrelevant_facts`, `fault_type`, `fault_agent`, `delete_fact`, `corrupt_fact`, `corrupt_replacement`, `expected_fault_handoff`.

No re-derivation examples yet. No v0b examples (faults at agents 1 or 3).

### `schemas.py` — EXISTS

Single source of truth for example validation. Enforces: all required fields present, no unexpected fields, `fault_type` in `VALID_FAULT_TYPES`, `expected_fault_handoff` matches `fault_type`, `needed_facts + irrelevant_facts == evidence` exactly, deletion rows have non-empty `delete_fact` in `needed_facts`, corruption rows have `corrupt_fact`/`corrupt_replacement`/`corrupted_answer`, clean/benign rows have no fault operation fields set. Raises `SchemaError` naming the example id and the exact bad field.

### `load_data.py` — EXISTS

Reads `fault_examples_v0a.jsonl`, calls `validate_dataset()` from `schemas.py`, returns the validated list or prints a per-row rejection report. Run directly to confirm the dataset is clean: `python load_data.py`.

---

## What Is Missing

### 1. v0b Dataset

v0b requires faults distributed across all three agents. The current 20 examples are all `fault_agent: 2`. We need:

- ~15–20 new examples where `fault_agent` is 1 or 3
- At least one set of **re-derivation** examples: fault injected at Agent 2 but the information is reconstructed by Agent 3 (agent is given enough context to re-derive)
- Suggested minimum for v0b: 10 examples per fault location (agent 1, 2, 3) × fault types relevant to that location

**Re-derivation example structure:** Same schema, `fault_type: "re_derivation"`, `fault_agent: 2`. The example must provide **two genuinely independent routes** to the answer — not just "enough left over." Route A (direct) is the deleted fact. Route B (derivation) must be a logically distinct path using *different* retained facts that reaches the same answer without Route A. Example: the answer is a year; Route A is the year stated directly (deleted); Route B is a retained duration + a retained start date from which the year can be computed independently. If Route B is a restatement of Route A in different wording, the example is invalid.

### 2. `build_messages.py`

Replaces the `agents/` directory. Single module that turns one validated example into the three deterministic agent messages.

- `m1` (Retriever output): `{known_facts: all evidence facts, reasoning_summary: "", answer_candidate: ""}`
- `m2_clean` (Reasoner output): same `known_facts` from m1, `reasoning_summary: ""`, `answer_candidate: ""`
- `m3` (Answerer output): built only from the faulted `m2` — **never** from the gold answer, original evidence, `needed_facts`, `delete_fact`, or `corrupt_replacement`

**Leakage rule:** `m3` must only receive the (post-injection) `m2`. Any leak of gold facts into `m3` would flatten the retention signal. For v0a, Agent 3 scoring (`m3`) may be skipped entirely; `R(m2_clean)` vs `R(m2_faulted)` is sufficient for detection.

**Note on what v0a tests:** Agent 2 does no reasoning. v0a tests the *measurement instrument* — does R drop when a needed fact is removed? It is not testing whether a real reasoning agent fails. That is the correct first test. The answer to "where's the reasoning?": deliberately absent in v0a to isolate the signal; added with hosted agents in v0b.

### 3. `inject_faults.py`

Applies exactly one controlled fault to the Agent 2 clean message. The fault spec is taken directly from the validated example's schema fields — never guesses which fact to touch.

- `clean`: return unchanged.
- `benign_compression`: remove only the `irrelevant_facts` entries from `known_facts`. **Decided:** explicit schema operation, not trusted to agent behavior. Valid only because `m2_clean` contains both needed and irrelevant facts, so removing irrelevant ones leaves `R_correct` at 1.
- `destructive_deletion`: remove exactly `delete_fact` from `known_facts`.
- `corruption`: replace `corrupt_fact` with `corrupt_replacement` in `known_facts`.

### 4. `reader.py`

The frozen measuring instrument. Given a message and the question, prompts the reader to answer from that message alone. Returns the **raw answer string** (or `UNKNOWN`) — not 1/0. Scoring against a specific target is handled in `scoring.py`.

Fixed across all runs: model name, prompt text, deterministic decoding. Three prompt variants are run per message for majority-vote stability (see Architecture section). All settings recorded in `results/run_manifest_v0a_<run_id>.json`.

### 5. `scoring.py`

Converts a reader output to 1 or 0 against a **specific target answer**. Signature: `score_answer(reader_output, target_answer) → int`. Target is always explicit — never hardcoded to gold:
- `R_correct` = `score_answer(output, example["answer"])`
- `R_corrupt` = `score_answer(output, example["corrupted_answer"])`

Normalization: lowercase, strip punctuation and whitespace. Numbers and units preserved so `"80 years"` ≠ `"45 years"`.

### 6. `retention.py`

Assembles per-message scores into the detection signal or retention curve.

- **v0a mode:** primary outputs are `R(m2_clean)` and `R(m2_faulted)`. Detection signal is `R(m2_clean) - R(m2_faulted)`. A drop is 1→0. No magnitude threshold.
- **v0b mode:** full curve `R(evidence) → R(m1) → R(m2) → R(final)`. Per-step drops computed; predicted fault handoff = argmax of drops.

### 7. `baselines.py`

Four dumb baselines that predict fault location without using retention (exercised in v0b where fault location varies):
- `blame_last`: always predict the last handoff
- `blame_random`: uniform random over three handoffs
- `blame_longest_message`: accuse the handoff with the longest output message
- `blame_shortest_message`: accuse the handoff with the shortest output message

### 8. `run_v0a.py`

The detection experiment end-to-end: examples → `build_messages` → `inject_faults` → `reader` → `scoring` → `retention` → outputs.

**Outputs three files:**
- `results/results_v0a.csv` — one row per example (columns below)
- `results/traces_v0a.jsonl` — full m1/m2_clean/m2_faulted/m3 messages + raw reader outputs per example
- `results/run_manifest_v0a_<run_id>.json` — reader model, prompt version, decoding settings, dataset hash, scoring version, date; stamped with run_id so old manifests are never overwritten

**Reader leakage controls run per example:**
- `no_context`: reader given empty message → should return UNKNOWN for fabricated facts
- `irrelevant_context`: reader given a different example's unrelated facts → should return UNKNOWN
- `memory_leak_flag = 1` if `R_correct(no_context) = 1`
- `hallucination_flag = 1` if reader gives unsupported answers that vary across prompts

### 9. `run_v0b.py`

Localization experiment. Same pipeline but fault location varies across agents 1, 2, 3. Outputs `results/results_v0b.csv` plus baseline comparison. **Built only after v0a passes.**

### 10. `analyze_results.py`

Reads a results CSV and produces:
- Summary table: accuracy by fault type, false-positive rate on benign compression, false-negative rate on deletion, corruption separation (`R_corrupt` rises where expected)
- Failure list: each failed example tagged as one of `bad_example`, `bad_injection`, `weak_reader`, `bad_scoring`, `real_weakness`

### 11. `results_v0a.csv` columns

```
id
fault_type
answer
corrupted_answer
R_correct_clean
R_correct_faulted
R_correct_no_context
R_correct_irrelevant_context
R_corrupt_clean
R_corrupt_faulted
reader_stability_clean
reader_stability_faulted
memory_leak_flag
hallucination_flag
detected_drop
expected_fault_handoff
pass_fail
```

For non-corruption rows, `R_corrupt_*` may be empty.

### 12. `results/run_manifest_v0a_<run_id>.json`

Written to `results/` before the run starts. Stamped with `run_id` so multiple runs do not overwrite each other. Two runs are only comparable if their manifests match on `reader_model`, `reader_prompt_version`, `decoding_config`, and `scoring_version`:

```json
{
  "reader_model": "",
  "reader_prompt_version": "",
  "decoding_config": {},
  "dataset_file": "",
  "dataset_hash": "",
  "scoring_version": "",
  "run_id": "",
  "timestamp": ""
}
```

### 13. `experiment_log.md`

One entry per run with: date, model stack, dataset size, fault types tested, what worked, what failed, next change.

### 14. `requirements.txt`

At minimum: inference client for the frozen reader, JSONL loaded natively (no dataset library needed for v0a).

---

## v0a Success Table

The expected signal per fault type — primary output of `analyze_results.py`:

| Fault type           | Expected R_correct_clean | Expected R_correct_faulted | Expected R_corrupt_faulted |
|----------------------|--------------------------|----------------------------|----------------------------|
| Clean                | 1                        | 1 (no fault applied)       | —                          |
| Benign compression   | 1                        | 1 (irrelevant facts only)  | —                          |
| Destructive deletion | 1                        | 0                          | —                          |
| Corruption           | 1                        | 0                          | 1                          |

---

## Key Open Decisions

1. **Reader model:** local Qwen2.5-7B vs. a weaker GPT-4o-mini call with a "do not use your knowledge" prompt. Local is cleaner for reproducibility; API is faster to get running.
2. **Binary vs. soft scoring:** start with binary exact match; switch to LLM judge if binary scores are too noisy on longer answers.

## Raise With PI Before Building

3. **v0b example construction:** a fault at Agent 1 must target a fact Agent 1 was specifically responsible for passing — not just a schema edit to `fault_agent`. Each new v0b example requires: (a) identifying which fact Agent 1 would have selected, (b) confirming the fault is genuinely decisive via counterfactual (would a correct Agent 1 output have fixed the final answer?). Reusing the 20 v0a examples by flipping `fault_agent` will not produce valid examples without this verification. Needs real construction. **Open question for PI:** how many examples per fault-type × fault-location cell does the signal test require to be statistically meaningful?

4. **v0b handoff labels:** fault at Agent 3 is not technically a handoff. Use these labels consistently for v0b:
   - `agent1_to_agent2` (fault at Agent 1)
   - `agent2_to_agent3` (fault at Agent 2)
   - `agent3_final_output` (fault at Agent 3)
   Update `schemas.py` and `EXPECTED_HANDOFF` when v0b dataset construction begins.

---

## Build Order

1. `schemas.py` + `load_data.py` — **already done**; run `python load_data.py` to confirm PASS
2. `build_messages.py` + `inject_faults.py` — produce clean and faulted messages; manually inspect one deletion example to confirm the fact is gone
3. `reader.py` + `scoring.py` — frozen reader + scorer; manually confirm `R_correct(m2_clean) = 1` on one clean example
4. `retention.py` — assemble the drop signal; confirm 1→0 fires on one deletion example
5. `run_v0a.py` — wire everything together; produce `results/results_v0a.csv`, `results/traces_v0a.jsonl`, `results/run_manifest_v0a_<run_id>.json`
6. `analyze_results.py` — read the CSV; check all rows of the v0a success table
7. `baselines.py` + `run_v0b.py` — **only after v0a passes**; extend dataset first
