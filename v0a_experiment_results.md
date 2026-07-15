# v0a Experiment Results

## 1. Verdict

**v0a PASSED — 19/20 examples pass the gate.**

The one failure (ex_011) is a documented reader-capability limitation, not a bug in the pipeline, fault injection, or scorer. The signal detection method is confirmed valid. The project proceeds to Phase 1.

---

## 2. Results Table

| Fault type | Pass / Total | Reader stability | Notes |
|---|---|---|---|
| clean | 5 / 5 | 3/3 on all 10 examples | No false drops. R_correct stays 1 through fault injection (clean = no-op). |
| benign_compression | 5 / 5 | 3/3 on all 10 examples | No false positives. Irrelevant facts stripped; answer-critical facts preserved. |
| destructive_deletion | 4 / 5 | 3/3 on 8/10; 1/3 on ex_011 clean | ex_011 fails due to reader limitation on clean message (see §3). |
| corruption | 5 / 5 | 3/3 on all 10 examples | R_correct drops to 0 on faulted; R_corrupt rises to 1 on faulted in all 5 cases. |
| **Overall** | **19 / 20** | | |

All passing examples had zero memory leaks (R_correct_no_context = 0) and zero hallucination flags.

---

## 3. The Single Failure: ex_011

**Example:** `ex_011` — fault type: `destructive_deletion`, answer: `1985`

**Question:** "What year was the company led by the engineer of Orbis-4 founded?"

**Clean message facts:**
- "The satellite Orbis-4 was engineered by Tomas Igby."
- "Tomas Igby leads the team at Nyra Aerospace."
- "Nyra Aerospace was founded in 1985."
- "Orbis-4 weighs 300 kilograms."

**Reader outputs on the clean message (m2_clean):**

| Prompt | Output | Correct? |
|---|---|---|
| 0 | `UNKNOWN — message does not provide enough information...` | No |
| 1 | `1985` | Yes |
| 2 | `UNKNOWN` | No |

**Majority vote: 1/3 → R_correct_clean = 0.** Gate requires R_correct_clean = 1, so example fails.

**Root cause:** The question requires a 3-hop reasoning chain: Orbis-4 → Tomas Igby → Nyra Aerospace → 1985. Prompts 0 and 2 use conservative phrasing ("not recoverable", "not stated or inferable") which caused the model to hedge with UNKNOWN even though all three facts are present. Prompt 1, which explicitly says "inferable", succeeded. This is a reader-strength issue, not a fault injection or scoring failure.

The faulted message correctly produces 0/3 UNKNOWN (the founding-year fact was deleted), and would satisfy the R_correct_faulted = 0 requirement — the detection direction is correct.

**ex_011 was left failing deliberately.** Patching the dataset or lowering the majority-vote threshold to force it green would hide a real reader limitation. It stands as early evidence that the reader model's multi-hop reasoning capability is a binding constraint — which directly motivates the reader ladder (weak → strong frozen reader) planned for Phase 2.

---

## 4. What v0a Proves

- **Retention drop reliably localizes injected faults.** On every example the reader could read (18 of 19 deletion/corruption examples), R_correct drops from 1 (clean) to 0 (faulted) exactly when the answer-critical fact is removed or corrupted.
- **Benign compression produces no false positives.** All 5 benign_compression examples score R_correct_clean = 1, R_correct_faulted = 1. The signal does not fire when irrelevant facts are stripped.
- **Corruption readback fires correctly.** All 5 corruption examples show R_correct_faulted = 0 (the corrupted value is not the gold answer) and R_corrupt_faulted = 1 (the reader reads the corrupted value faithfully from the faulted message). This validates the two-channel scoring design.
- **The clean-vs-faulted signal gap held on every readable example.** There are zero cases where a readable clean message + injected fault failed to produce a drop. The signal is clean.
- **No memory leaks.** R_correct_no_context = 0 for all 20 examples. The reader is not drawing on parametric knowledge; it answers only from the provided message.

---

## 5. Run Info

| Field | Value |
|---|---|
| Run ID | `20260713_035345` |
| Timestamp | 2026-07-13T03:53:45 UTC |
| Reader model | `Qwen/Qwen2.5-7B-Instruct` |
| Reader prompt version | `v1` (3 prompt variants, majority vote 2/3) |
| Decoding config | `max_new_tokens: 50`, `do_sample: false` |
| Scoring version | `v2_bridge` (commitment-check: word-boundary + negation + ambiguity + compound-entity guards) |
| Dataset file | `fault_examples_v0a.jsonl` |
| Dataset hash | `b8ab17f61d3c55b4` |
| Examples | 20 (5 each: clean, benign_compression, destructive_deletion, corruption) |
| Infrastructure | Azure VM (`retention-vm`, azureuser) |

> **Note on scoring version:** The manifest file on disk (`run_manifest_v0a_20260713_035345.json`) records `scoring_version: v1` — this reflects the first VM run. The results CSV and traces in this repo are from a subsequent re-run after `scoring.py` was upgraded to `v2_bridge`. The v2_bridge run manifest was not separately pushed. All results in §2 reflect v2_bridge scoring.

---

## 6. Decision

**v0a gate is passed. Committing to Phase 1 (benchmark construction).**

The core signal — retention score drops when an answer-critical fact is removed or corrupted at Agent 2 — is confirmed on controlled synthetic data.

The v2_bridge scorer (deterministic string commitment check) was sufficient for v0a. A frozen, human-validated LLM judge is a deferred Phase 1 deliverable and was not introduced here.

The reader limitation documented in ex_011 is accepted as-is. It informs the Phase 2 reader ladder: reader capability must be treated as a variable, not a constant, in the full evaluation design.
