# Evaluation Decisions

This file records deferred evaluation design decisions and their rationale.
It is a binding commitment list, not a wish list.

---

## Decision 1 — Scoring method for Phase 0 (v0a)

**What was used:** A minimal deterministic commitment-check scorer (`v2_bridge`).

The scorer normalizes both reader output and target answer (lowercase, strip edge punctuation, strip one leading article), then checks whether the target appears as a whole-phrase word-boundary match in the output. Three guards rule out false positives: a negation guard (e.g. "not 1990"), an ambiguity guard (e.g. "1990 or 1991"), and a compound-entity guard (output is a named-entity extension of the target, e.g. "Merrow Academy" vs "Merrow"). No model calls; fully deterministic string logic.

**Why this was sufficient for v0a:** v0a is a signal check on controlled synthetic data with clean gold answers. The scorer only needs to distinguish "reader commits to the target" from "reader says UNKNOWN or something else". The synthetic answers are short and unambiguous (years, city names, single entities). The commitment-check handles the main failure mode from v1 (correct answers embedded in full sentences scoring 0).

**What is deferred:** The full evaluation method for Paper 1.

---

## Decision 2 — Full LLM judge for Paper 1 (DEFERRED, committed Phase 1 deliverable)

**Status: NOT OPTIONAL. Must be completed before any Paper 1 result is reported.**

### Design specification

The full evaluation method is a **frozen LLM judge** that reads a reader output and classifies it into one of four labels:

| Label | Meaning |
|---|---|
| `gold` | Output commits to the gold answer |
| `different-definite` | Output commits to a specific answer that is not the gold answer |
| `ambiguous` | Output presents multiple candidates without committing |
| `no-answer` | Output declines to answer (UNKNOWN, hedge, refusal) |

This replaces the binary exact-match / commitment-check approach. It captures the distinction between a reader that says UNKNOWN (information is lost) and one that says a wrong-but-definite answer (corruption is present).

### Freezing requirements

The judge must be frozen before any benchmark results are reported:

1. **Model:** A specific versioned checkpoint must be chosen and locked (e.g. `gpt-4o-2024-08-06`). The model identifier is recorded in the run manifest under `judge_model`.
2. **Prompt:** The judge prompt must be versioned (e.g. `judge_prompt_v1`) and stored in the repository. It must not be changed after human validation begins.
3. **Manifest recording:** Every evaluation run manifest must record `judge_model`, `judge_prompt_version`, and `judge_scoring_version` alongside the reader model fields.

### Human validation requirement

Before the judge is used to report any result, it must be validated against human labels on a **50–100 example sample** drawn from the benchmark. The validation report must record:

- Judge-vs-human agreement rate (target: ≥ 0.90)
- Breakdown by label (especially `different-definite` vs `ambiguous` — the hardest boundary)
- Any systematic disagreements and how they were resolved

The validation sample and labels must be stored in the repository under `evaluation/judge_validation/`.

### Why this matters

The commitment-check bridge (v2_bridge) cannot distinguish `different-definite` from `ambiguous`. For corruption experiments this distinction is critical: a reader that reads a corrupted value and commits to it is different from a reader that hedges. Paper 1's main claims depend on this distinction being measured correctly.

---
