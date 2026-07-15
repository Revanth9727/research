# v0b Build Plan

**For PI approval — July 2026**

---

## What v0b Tests

v0b tests whether a retention-score drop reliably identifies *where in the pipeline information stops being recoverable* — specifically, whether the fault occurred at Agent 1 (Retriever) or Agent 2 (Reasoner). This is a transmission-fault localization test, not a reasoning-quality test.

**Out of scope by PI ruling:**
- **Agent-3 faults** are excluded. An Agent-3 failure is a compute failure after successful transmission — the facts are intact in the message, so a fact-recoverability method should not and cannot catch it. It belongs to a future experiment on reasoning failures.
- **Re-derivation** is excluded. It requires the reader to follow multi-hop inference chains, which v0a already showed breaks the reader (ex_011). Including it would contaminate the localization test by introducing a reader-reliability variable.

v0b is scoped to **transmission faults only: Agent 1 and Agent 2.**

---

## The Dataset

25 examples, already built and validated — not generated as part of this build:

| Group | Count | Fault type | Expected handoff |
|---|---|---|---|
| Agent-1 faults | 10 | 5 destructive_deletion + 5 corruption | `agent1_to_agent2` |
| Agent-2 faults | 10 | 5 destructive_deletion + 5 corruption | `agent2_to_agent3` |
| Clean controls | 5 | none | `none` |

Chains are deliberately 2-hop and direct (no multi-hop inference required) so the reader scores 1 reliably on clean messages. Reader reliability is a controlled constant in a localization test, not a variable — the whole point is to isolate *where* the drop happens, not *whether* the reader is strong enough.

---

## The 6 Build Steps

1. **`schemas.py`** — extend validation to allow `fault_agent` values 1 and 2, and make the expected-handoff check key off the fault agent (agent 1 → `agent1_to_agent2`, agent 2 → `agent2_to_agent3`). ~15 lines changed in one file.

2. **`inject_faults.py`** — add `inject_into_m1()`, which applies deletion or corruption to Agent 1's outgoing message using the same deterministic schema-field logic already used for Agent 2. No `inject_into_m3()`. ~20 lines added to one file.

3. **`build_messages.py`** — add an evidence message (the raw facts as a scorable message, forming the curve's starting point) and a `build_v0b_messages()` function that routes the fault to the correct agent and returns all four messages needed for the retention curve. ~25 lines added to one file.

4. **`retention.py`** — implement the approved clean-control threshold in the existing `compute_v0b_curve()` stub. ~4 lines changed in one file.

5. **`run_v0b.py`** — new experiment runner: loads the v0b dataset, builds messages, scores the full retention curve with the frozen reader, predicts fault location, runs all four baselines, and writes results. ~180 lines, one new file.

6. **`analyze_v0b.py`** — new analysis script: reads `results_v0b.csv`, prints per-agent localization accuracy, the baseline comparison table, and the v0b gate verdict. ~150 lines, one new file.

---

## The Threshold Decision

With binary scoring, retention values at each step are either 0 or 1. A "drop" at a handoff is the difference between consecutive steps.

**Rule:** if no adjacent step in the curve drops from 1 to 0, predict `none` (no fault detected). If at least one step drops 1→0, predict the handoff where that drop occurs.

This is not a tunable continuous parameter — it follows directly from binary scoring. A flat curve (all 1s) means no transmission fault is detectable. Forcing a location prediction on a flat curve would produce false positives on clean examples.

---

## v0b Gate Criteria

All four must hold for v0b to pass:

1. **Beats random** — localization accuracy > 50% on fault examples (random chance on 2 locations is 50%).
2. **Beats blame_last** — accuracy exceeds the always-predict-Agent-2 heuristic.
3. **Beats blame_longest and blame_shortest** — accuracy exceeds message-length-based heuristics.
4. **Low clean-control false-positive rate** — the method predicts `none` on clean examples; a false positive is predicting a fault location when there is none.

---

## What v0b Will and Won't Prove

**Will prove:** whether a retention-score drop, computed over the 4-point curve R(evidence) → R(m1) → R(m2) → R(final), correctly identifies the faulted agent better than simple uninformed heuristics — on controlled synthetic data with transmission faults only.

**Won't prove:**
- Whether the method works on Agent-3 reasoning failures (different problem class, deferred).
- Whether the method handles multi-hop chains or re-derivation patterns (reader capability limit, deferred to Phase 2 reader-ladder work).
- Whether the method generalizes to real pipeline outputs with generation noise (live agents are added in Phase 1).

If v0b passes, the project commits to Phase 1: benchmark construction with a larger varied dataset and live agent generation.
