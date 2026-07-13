# Project Plan

## Measuring Information Survival in Multi-Agent LLM Pipelines

*Draft, July 2026*

---

## Problem

When a team of LLM agents works together and the answer is wrong, we cannot reliably tell which agent caused it, so the whole pipeline gets rerun instead of fixing one step. Existing methods (LLM-judge, Famas, AgenTracer, GraphTracer) judge transcripts or trace dependencies. None distinguishes an agent that correctly trimmed irrelevant detail from one that destroyed the information the answer needed. Both look like "the text got shorter." Only one is a fault.

## Central idea

Instead of judging which agent appears responsible, measure whether the information the task needs actually survives each handoff. Each inter-agent message is an information bottleneck; we quantify how much task-relevant information passes through it. A sharp drop flags a candidate failure point.

Guiding hypothesis: localization improves when we treat failures as fundamentally different types (benign compression, destructive deletion, corruption), and we operationalize that with an information-retention estimator.

## Approach

1. Prove the core signal works on a tiny synthetic prototype (kill-check first).
2. Scale it into a released benchmark of typed faults (Paper 1).
3. Build the full localization method on that benchmark and compare against the field (Paper 2).

Every phase has a gate so we fail cheap if the idea does not hold.

## The hardest question, tracked throughout

Agents compute, they don't just carry information. An agent can delete a fact that a later agent re-derives, so "information survived" and "the pipeline worked" are not identical. We treat this drop-then-recovery event as a detectable finding, not noise, and the prototype is built to test it directly.

## Phases and timeline

Working at ~15 hrs/week.

### Phase 0 — Prototype / go-no-go (weeks 1-2)
Build 20-50 synthetic multi-hop QA examples, a 3-agent JSON pipeline, and the retention score. Run in two stages:
- **v0a (detection):** faults only at Agent 2. Does retention drop when needed information is removed?
- **v0b (localization):** faults at Agent 1, 2, or 3. Does the largest drop point to the correct handoff? Fault location must vary for this to be a real localization test.
- Gate: beats random, beats blame-last, beats shortest/longest-message, does not false-flag benign compression, detects drop-then-recovery, and separates deletion (R_correct drops) from corruption (R_correct drops and R_corrupt rises).
- If it fails, stop here. Two weeks lost, not a year.

### Phase 1 — Benchmark, Paper 1 (months 1-4)
Scale the synthetic set; add filtered HotpotQA and naturally occurring failures from real agent runs; verify faults by counterfactual replay so the injected fault is genuinely decisive. Mix injected and natural faults so the benchmark cannot be dismissed as built to favor our method.
- Deliverable: released typed-fault benchmark with negative controls. Submit as Paper 1.

### Phase 2 — Method, Paper 2 (months 4-9)
Full retention estimator; reader-ladder calibration (weak-to-strong readers to separate real loss from reader weakness); head-to-head on Who&When against LLM-judge, AgenTracer, GraphTracer; repair experiment (locate culprit, rerun only that agent, measure fix rate).
- Deliverable: the method paper.

### Phase 3 — Generalization and write-up (months 9-12)
One coding or retrieval pipeline as a generalization check; sensitivity analyses over reader model, chain length, message length; final submissions.

## Key decisions (prototype version)

- **Agents:** hosted API model, for speed.
- **Reader:** separate frozen open-weight model, held fixed across runs.
- **Scoring:** exact answer recovery first, LLM judge second.
- **Message format:** structured JSON (`known_facts`, `reasoning_summary`, `answer_candidate`).
- **Fault types:** benign compression, destructive deletion, corruption, re-derivation.

## Assumptions (tested, not assumed)

1. Task-relevant information is represented in the intermediate messages.
2. Downstream agents primarily consume those messages rather than regenerate missing information.
3. Recoverability under a strong reader approximates recoverability for the downstream agent.

Assumption 2 is most at risk and is the focus of the make-or-break prototype test.

## Data constraint

All datasets open and public. Who&When is public, our benchmark is released openly, open-weight models serve as frozen readers for reproducibility. Trace-generation models unrestricted.

## Two-paper rationale

The benchmark is the safer, higher-citation first paper and may prove more influential; it is useful to the field independent of our method. The method paper depends on the benchmark for ground truth, so building the benchmark first is the natural order.

## Out of scope (noted, not modeled)

Aggressive-but-recoverable compression can keep the answer recoverable while forcing far more downstream reasoning, making the pipeline more fragile. Flagged as future work rather than modeled here.

## One-line pitch

Everyone races to guess which agent broke. We measure whether the information the task needs actually survived, and separate agents that compressed from agents that destroyed.
