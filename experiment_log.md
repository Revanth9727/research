# Experiment Log

---

## 2026-07-13 — v0a gate run

**Purpose:** Phase 0 v0a — verify that the retention signal drops when an answer-critical fact is removed or corrupted at Agent 2 on controlled synthetic data.

**Setup:**
- Model: `Qwen/Qwen2.5-7B-Instruct`
- Scoring: `v2_bridge` (deterministic commitment-check: word-boundary + negation + ambiguity + compound-entity guards)
- Dataset: `fault_examples_v0a.jsonl` — 20 examples (5 each: clean, benign_compression, destructive_deletion, corruption)
- Infrastructure: Azure VM (`retention-vm`)

**Result: v0a PASSED — 19/20 examples pass the gate.**

| Fault type | Pass / Total |
|---|---|
| clean | 5 / 5 |
| benign_compression | 5 / 5 |
| destructive_deletion | 4 / 5 |
| corruption | 5 / 5 |

**The one failure — ex_011:**
- Fault type: `destructive_deletion`, answer: `1985`
- Failed because the reader could not recover the answer from the **clean** message (R_correct_clean = 0), before any fault was applied.
- Root cause: the question requires a 3-hop reasoning chain (Orbis-4 → Tomas Igby → Nyra Aerospace → 1985). Two of three reader prompts returned UNKNOWN on the clean message; majority vote was 1/3.
- **Left unfixed deliberately.** Patching the dataset or relaxing the threshold would hide a real reader limitation. It is documented evidence that reader multi-hop capability matters — directly motivating the reader ladder in Phase 2.

**Verdict:** Gate passed. Committing to Phase 1 (benchmark construction).

**See also:** `v0a_experiment_results.md` for the full analysis.

---
