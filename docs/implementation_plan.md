# Implementation Plan

## Measuring Information Survival in Multi-Agent LLM Pipelines
### What I will code, and why each piece exists

*v0a scope, July 2026*

---

## What v0a proves

That when an answer-needed fact is removed or corrupted at Agent 2, the binary retention score drops (1 -> 0) at the `agent2_to_agent3` handoff, while clean and benign-compression examples stay at 1. It is a signal check on controlled synthetic data.

## What v0a does NOT prove

It does not prove localization (fault location does not vary yet), does not make statistical claims (sample too small), does not test re-derivation, and does not touch real benchmarks. Those are v0b and later.

---

## Module map

Each module has one job. Data flows top to bottom: raw examples -> messages -> faulted messages -> reader scores -> retention curve -> results.

### `schemas.py`
**Purpose:** single source of truth for what a valid example looks like.
**Why it exists:** every downstream module assumes the fields are present and well-formed. Validating once, up front, means no module has to guess or defensively re-check.
**In:** a parsed example dict.
**Out:** pass, or a clear error naming the bad field.
**Key rule:** enforces that deletion rows have `delete_fact`, corruption rows have `corrupt_fact` + `corrupt_replacement` + `corrupted_answer`, and every fact in `delete_fact`/`corrupt_fact` actually exists in `needed_facts`. This is what stops a fault from silently missing.

### `load_data.py`
**Purpose:** read the JSONL and hand back validated examples.
**Why it exists:** keeps file I/O and schema-checking in one place so experiment scripts stay clean.
**In:** path to `fault_examples_v0a.jsonl`.
**Out:** list of validated example dicts; a report of any rows rejected and why.

### `build_messages.py`
**Purpose:** turn one example into the three agent messages (Retriever, Reasoner, Answerer) via deterministic templating from the example fields.
**Why it exists:** the "clean" pipeline is the baseline every fault is measured against. For v0a it is built by code templates, not hosted agents, so a failed run points to the idea, not to generation noise.
**In:** one example.
**Out:** `m1`, `m2_clean`, `m3` message objects (`known_facts`, `reasoning_summary`, `answer_candidate`), no faults applied.
**Key rule:** Agent 3 (`m3`) is constructed only from the (later faulted) Agent 2 message. It must never receive the gold `answer`, original `evidence`, `needed_facts`, `delete_fact`, or `corrupt_replacement`, or it will leak the answer and flatten the retention curve.

### `inject_faults.py`
**Purpose:** apply exactly one controlled fault to the Agent 2 message.
**Why it exists:** this is the experiment's independent variable. It must be surgical and deterministic, never guessing which fact to touch.
**In:** the clean Agent 2 message + the example's fault spec.
**Out:** the faulted Agent 2 message.
**Behavior by type:**
- benign_compression: drop only `irrelevant_facts`. Valid only because the clean `m2` contains both needed and irrelevant facts, so removing irrelevant ones leaves `R_correct` at 1 (no drop).
- destructive_deletion: remove exactly `delete_fact`.
- corruption: replace `corrupt_fact` with `corrupt_replacement`.
- clean: return unchanged.

### `reader.py`
**Purpose:** the frozen measuring instrument. Given a message and the question, ask the reader to answer from that message alone.
**Why it exists:** the whole method depends on one fixed, deterministic reader. Isolating it here guarantees the same model, prompt, and decoding settings across every run.
**In:** a message, the question.
**Out:** the reader's raw answer string (or UNKNOWN).
**Fixed:** model name, prompt text, deterministic decoding. All recorded, never changed mid-experiment.

### `scoring.py`
**Purpose:** decide whether a reader output recovers a *target* answer.
**Why it exists:** recoverability is only meaningful against a specific target. Corruption needs two passes — gold and corrupted — so the target must be a parameter.
**In:** `reader_output`, `target_answer`.
**Out:** 1 or 0.
**Key rule:** signature is `score_answer(reader_output, target_answer)`, never hardcoded to gold. R_correct = score against `answer`; R_corrupt = score against `corrupted_answer`. Normalization: casing, punctuation, whitespace only — numbers and units preserved so "80 years" and "45 years" stay distinct.

### `retention.py`
**Purpose:** assemble per-message scores into a retention curve and find the drop.
**Why it exists:** this is where the raw scores become the actual signal the project is about.
**In:** the sequence of R_correct scores across messages (plus R_corrupt for corruption rows).
**Out:** the retention curve, the handoff where 1 -> 0 occurs, and the predicted fault handoff.
**Key rule:** a drop is 1 -> 0 between adjacent messages. No magnitude threshold in v0.

### `baselines.py`
**Purpose:** the dumb comparators the method must beat (used in v0b).
**Why it exists:** beating chance is not enough; the signal only matters if it beats blame-last, longest-message, and shortest-message too.
**In:** the messages / chain.
**Out:** each baseline's predicted culprit handoff.
**Note:** built now, exercised in v0b where fault location varies.

### `run_v0a.py`
**Purpose:** the detection experiment end to end.
**Why it exists:** one command that goes examples -> messages -> fault -> reader -> score -> curve -> outputs, so runs are reproducible.
**In:** the dataset.
**Out:** three files:
- `results/results_v0a.csv` — one row per example: fault_type, `R_correct` on `m2_clean` and `m2_faulted`, `R_corrupt` where relevant, detected drop, match against `expected_fault_handoff`.
- `results/traces_v0a.jsonl` — full `m1`/`m2_clean`/`m2_faulted`/`m3` messages and raw reader outputs per example, for inspecting failures.
- `run_manifest.json` — reader model, prompt version, decoding settings, dataset hash, scoring version, date.
**Main comparison:** `R(m2_clean)` vs `R(m2_faulted)`, which isolates whether the injected fault caused the loss.

### `run_v0b.py`
**Purpose:** the localization experiment (later).
**Why it exists:** same pipeline but fault location varies, so the method is compared against baselines.
**In:** the v0b dataset.
**Out:** `results/results_v0b.csv` plus baseline comparison.

### `analyze_results.py`
**Purpose:** turn the CSV into human-readable tables and a failure list.
**Why it exists:** the numbers only help if they are summarized and the failures are classified.
**In:** a results CSV.
**Out:** accuracy by fault type, false-positive rate on benign compression, false-negative rate on deletion, corruption separation, and a list of failed examples each tagged as bad example / bad injection / weak reader / bad scoring / real weakness.

---

## Build order

1. `schemas.py` + `load_data.py` — nothing runs without validated data.
2. `build_messages.py` + `inject_faults.py` — produce clean and faulted messages.
3. `reader.py` + `scoring.py` — the measuring instrument and its scorer.
4. `retention.py` — turn scores into the drop signal.
5. `run_v0a.py` — wire it together, produce the CSV.
6. `analyze_results.py` — read the result.
7. `baselines.py` + `run_v0b.py` — only after v0a passes.

## Known risks

- **Reader too weak:** reports loss that a stronger reader would recover. Mitigation: reader ladder later; for v0a, pick a capable instruct model and record it.
- **Scoring too strict/loose:** exact match may miss valid paraphrases or accept near-misses. Mitigation: normalization rules fixed up front; upgrade to logprob/MCQ after v0a.
- **Fault silently ineffective:** a deleted fact the reader recovers anyway. Mitigation: schema guarantees the fact was answer-bearing; manual review of any example where clean and faulted scores match.
- **Tiny sample:** 20 examples show signal, not significance. Mitigation: stated explicitly; v0b scales per cell before any baseline claim.

## Final v0a decisions before coding

1. v0a uses deterministic templated messages, not hosted agent generation. Hosted agents are added only after the retention signal works in the controlled setting. (Rationale: v0a is a signal check; generation noise would make a failure impossible to diagnose.)
2. The main v0a comparison is `R(m2_clean)` vs `R(m2_faulted)`. That isolates whether the injected fault caused recoverability loss.
3. Message positions are named: `m1` (Retriever), `m2_clean`, `m2_faulted`, `m3` (Answerer, from `m2_faulted` only).
4. Agent 3 must never receive the gold answer, original evidence, `needed_facts`, `delete_fact`, or `corrupt_replacement` after fault injection. It sees only the faulted Agent 2 message. For the first deterministic v0a, Agent 3 scoring may be skipped entirely; `R(m2_clean)` vs `R(m2_faulted)` is enough for detection.
5. `expected_fault_handoff` is `"none"` for clean and benign-compression rows, and `"agent2_to_agent3"` for destructive deletion and corruption. (Dataset updated accordingly.)
6. Benign compression is only valid if the clean Agent 2 message contains both needed and irrelevant facts before compression; the fault removes only irrelevant facts, so `R_correct` stays 1 (no drop).
7. Every run writes both `results_v0a.csv` and `results/traces_v0a.jsonl` (full messages and reader outputs per example, for debugging when the CSV isn't enough).
8. Every run writes a `run_manifest.json` recording reader model, prompt version, decoding settings, dataset hash, scoring version, and date, so any run is reproducible.

## The v0a success table (main output of analyze_results.py)

| Fault type | Expected signal |
| --- | --- |
| Clean | R_correct stays 1 |
| Benign compression | R_correct stays 1 |
| Destructive deletion | R_correct goes 1 -> 0 |
| Corruption | R_correct goes 1 -> 0 and R_corrupt goes 0 -> 1 |

## Open decision before first run

Pick and record the exact frozen reader model (name + version + decoding settings). Everything downstream assumes it is fixed.

## Reader leakage controls

For every example, the reader is tested under four conditions:

1. `m2_clean`
2. `m2_faulted`
3. `no_context`: empty message or "No information provided."
4. `irrelevant_context`: a message built from another example's unrelated facts

Purpose:
- If the reader answers correctly from `m2_clean` but not from `no_context` or `irrelevant_context`, recovery is message-supported (the only case that counts as clean recoverability).
- If the reader answers correctly from `no_context`, set `memory_leak_flag = 1` — the example is contaminated for retention measurement.
- If the reader gives unsupported answers that vary across prompts, set `hallucination_flag = 1`.

For synthetic fabricated-fact examples, `no_context` recovery should almost always be 0; the controls exist to prove that, and become essential once real facts (HotpotQA) enter later.

This is a diagnostic layer, not the core v0a metric. The core metric remains `R(m2_clean)` vs `R(m2_faulted)`. The controls exist to rule out the objection that a drop is explained by memory rather than genuine information loss.

## Reader prompt variants (majority vote)

To separate stable recovery from prompt-sensitive noise, each message is scored with three prompt phrasings (later factored into `prompts.py`):

1. "Given only the message below, answer the question. If the answer is not recoverable, output UNKNOWN."
2. "Use only the provided message. Do not use outside knowledge. Return only the answer, or UNKNOWN if the answer is not stated or inferable."
3. "Can the question be answered from this message alone? If yes, return the answer. If no, return UNKNOWN."

v0a scoring rule: `R = 1` if at least 2 of 3 prompts recover the target answer, else `R = 0`. Also log the raw rate (e.g. 2/3) as `reader_stability` for diagnostics.

## results_v0a.csv columns

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
