"""
retention.py — retention scoring utilities for v0a and v0b.

Key functions:
  majority_vote(raw_outputs, target)      -> (R, stability_str)
  compute_v0a_signal(R_correct_clean, R_correct_faulted) -> dict
  compute_pass_fail(row)                  -> "pass" | "fail"

v0a mode: primary signal is R(m2_clean) vs R(m2_faulted) — a paired comparison.
v0b mode: full curve R(evidence)->R(m1)->R(m2)->R(final); argmax drop predicts
          the fault handoff. Stub included; exercised in run_v0b.py.
"""

from __future__ import annotations

from scoring import score_answer, SCORING_VERSION

V0B_HANDOFFS = ["agent1_to_agent2", "agent2_to_agent3", "agent3_final_output"]


def majority_vote(raw_outputs: list[str], target: str) -> tuple[int, str]:
    """
    Score a list of raw reader outputs against a target answer by majority vote.

    Returns (R, stability) where:
      R = 1 if at least 2 of 3 prompts recover the target, else 0.
      stability = "2/3" format string logged as reader_stability for diagnostics.
    """
    scores = [score_answer(o, target) for o in raw_outputs]
    total = sum(scores)
    R = 1 if total >= 2 else 0
    stability = f"{total}/{len(raw_outputs)}"
    return R, stability


def compute_v0a_signal(R_correct_clean: int, R_correct_faulted: int) -> dict:
    """
    Compute the v0a detection signal from paired clean/faulted R_correct scores.

    A drop is 1→0. No magnitude threshold.

    Returns:
      drop: R_correct_clean - R_correct_faulted (0 or 1 for binary scores)
      detected_drop: 1 if clean=1 and faulted=0, else 0
    """
    drop = R_correct_clean - R_correct_faulted
    detected_drop = 1 if (R_correct_clean == 1 and R_correct_faulted == 0) else 0
    return {"drop": drop, "detected_drop": detected_drop}


def compute_pass_fail(row: dict) -> str:
    """
    Evaluate the v0a gate for one example row.

    row must contain: fault_type, R_correct_clean, R_correct_faulted,
    R_corrupt_faulted (int or ""), memory_leak_flag.

    Gate conditions (from phase0.md):
      clean / benign_compression : R_cc=1 and R_cf=1
      destructive_deletion       : R_cc=1 and R_cf=0
      corruption                 : R_cc=1 and R_cf=0 and R_rf=1
      any                        : memory_leak_flag=0
    """
    if row.get("memory_leak_flag"):
        return "fail"

    ft = row["fault_type"]
    R_cc = row["R_correct_clean"]
    R_cf = row["R_correct_faulted"]

    if ft in ("clean", "benign_compression"):
        return "pass" if (R_cc == 1 and R_cf == 1) else "fail"

    if ft == "destructive_deletion":
        return "pass" if (R_cc == 1 and R_cf == 0) else "fail"

    if ft == "corruption":
        R_rf = row.get("R_corrupt_faulted", "")
        return "pass" if (R_cc == 1 and R_cf == 0 and R_rf == 1) else "fail"

    return "fail"


def compute_v0b_curve(scores: dict[str, int]) -> dict:
    """
    Compute the v0b retention curve and predict the fault handoff.

    scores: {"R_evidence": int, "R_m1": int, "R_m2": int, "R_final": int}

    Prediction rule — first-transition:
      Walk the curve in order: evidence → m1 → m2 → final.
      Predict the handoff at the FIRST adjacent step where R goes from 1 to 0.
      If no step drops 1→0 (flat curve, e.g. clean controls), predict "none".

    Rationale: once information is lost (R=0), it stays lost downstream.
    The first 1→0 transition is the causal origin of the fault; a later
    drop is merely the fault propagating, not a new fault location.
    """
    ordered = [
        ("agent1_to_agent2",    scores.get("R_evidence", 1), scores.get("R_m1", 1)),
        ("agent2_to_agent3",    scores.get("R_m1", 1),       scores.get("R_m2", 1)),
        ("agent3_final_output", scores.get("R_m2", 1),       scores.get("R_final", 1)),
    ]
    drops = {label: before - after for label, before, after in ordered}

    predicted = "none"
    for label, before, after in ordered:
        if before == 1 and after == 0:
            predicted = label
            break

    return {
        "curve":                   {label: after for label, _, after in ordered},
        "drops":                   drops,
        "predicted_fault_handoff": predicted,
    }
