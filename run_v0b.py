"""
run_v0b.py — v0b localization experiment end-to-end.

Per example:
  1. Build the full message set (evidence, m1, m2, m3) with the fault routed
     to the correct agent via build_v0b_messages().
  2. Score the retention curve: R(evidence) → R(m1) → R(m2) → R(final).
  3. Predict the fault handoff via first-transition logic (compute_v0b_curve).
  4. Run the four dumb baselines and record their predictions.
  5. Compare prediction to expected_fault_handoff → correct_localization.

Outputs:
  results/results_v0b.csv
  results/traces_v0b.jsonl
  results/run_manifest_v0b_<run_id>.json

Exit code 0 if all v0b gate criteria pass, 1 otherwise.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from build_messages import build_v0b_messages
from reader import read_all_prompts, manifest_entry
from retention import majority_vote, compute_v0b_curve, SCORING_VERSION
from baselines import run_all_baselines
from scoring import score_answer

_JSONL_PATH = Path(__file__).resolve().parent / "v0b_examples.jsonl"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"

_CSV_COLUMNS = [
    "id", "fault_type", "fault_agent", "answer", "corrupted_answer",
    "R_evidence", "R_m1", "R_m2", "R_final",
    "reader_stability_evidence", "reader_stability_m1",
    "reader_stability_m2", "reader_stability_final",
    "predicted_handoff", "expected_fault_handoff", "correct_localization",
    "baseline_blame_last", "baseline_blame_random",
    "baseline_blame_longest", "baseline_blame_shortest",
    "drop_agent1_to_agent2", "drop_agent2_to_agent3", "drop_agent3_final_output",
    "R_corrupt_m2", "R_corrupt_final",
    "pass_fail",
]


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def _v0b_gate(rows: list[dict]) -> tuple[bool, dict]:
    """
    Evaluate all four v0b gate criteria.
    Returns (all_pass, details_dict).
    """
    fault_rows  = [r for r in rows if r["expected_fault_handoff"] != "none"]
    clean_rows  = [r for r in rows if r["expected_fault_handoff"] == "none"]

    n_fault = len(fault_rows)
    n_clean = len(clean_rows)

    # Retention method accuracy on fault examples
    retention_correct = sum(r["correct_localization"] for r in fault_rows)
    retention_acc = retention_correct / n_fault if n_fault else 0.0

    # Baseline accuracies on fault examples
    def baseline_acc(key):
        correct = sum(1 for r in fault_rows if r[key] == r["expected_fault_handoff"])
        return correct / n_fault if n_fault else 0.0

    bl_last     = baseline_acc("baseline_blame_last")
    bl_random   = baseline_acc("baseline_blame_random")
    bl_longest  = baseline_acc("baseline_blame_longest")
    bl_shortest = baseline_acc("baseline_blame_shortest")

    # Clean-control false-positive rate
    fp = sum(1 for r in clean_rows if r["predicted_handoff"] != "none")
    fp_rate = fp / n_clean if n_clean else 0.0

    beats_random   = retention_acc > 0.5
    beats_last     = retention_acc > bl_last
    beats_longest  = retention_acc > bl_longest
    beats_shortest = retention_acc > bl_shortest
    low_fp         = fp_rate <= 0.20

    all_pass = all([beats_random, beats_last, beats_longest, beats_shortest, low_fp])

    details = {
        "retention_accuracy":    retention_acc,
        "baseline_blame_last":   bl_last,
        "baseline_blame_random": bl_random,
        "baseline_blame_longest": bl_longest,
        "baseline_blame_shortest": bl_shortest,
        "clean_fp_rate":         fp_rate,
        "beats_random":          beats_random,
        "beats_last":            beats_last,
        "beats_longest":         beats_longest,
        "beats_shortest":        beats_shortest,
        "low_fp":                low_fp,
        "n_fault":               n_fault,
        "n_clean":               n_clean,
    }
    return all_pass, details


# ---------------------------------------------------------------------------
# Main experiment loop
# ---------------------------------------------------------------------------

def run(path: Path) -> int:
    from load_data import load_and_validate

    if not path.exists():
        print(f"Dataset not found: {path}")
        print("Place v0b_examples.jsonl in the repo root before running.")
        return 1

    try:
        examples = load_and_validate(path)
    except Exception as e:
        print(f"Dataset validation error: {e}")
        return 1

    _RESULTS_DIR.mkdir(exist_ok=True)

    run_id   = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = _RESULTS_DIR / "results_v0b.csv"
    jsonl_path = _RESULTS_DIR / "traces_v0b.jsonl"
    manifest_path = _RESULTS_DIR / f"run_manifest_v0b_{run_id}.json"

    dataset_hash = hashlib.md5(path.read_bytes()).hexdigest()[:16]

    reader_config = manifest_entry()
    manifest = {
        **reader_config,
        "dataset_file":   str(path),
        "dataset_hash":   dataset_hash,
        "scoring_version": SCORING_VERSION,
        "run_id":         run_id,
        "timestamp":      datetime.now().isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written: {manifest_path.name}")
    print(f"Dataset: {len(examples)} examples  hash={dataset_hash}\n")

    rows:   list[dict] = []
    traces: list[dict] = []

    for i, ex in enumerate(examples, 1):
        ex_id = ex["id"]
        print(f"[{i:02d}/{len(examples)}] {ex_id}  fault_type={ex['fault_type']}  "
              f"fault_agent={ex['fault_agent']}")

        msgs = build_v0b_messages(ex)

        # Score the four curve points
        raw: dict[str, list[str]] = {}
        R:   dict[str, int]       = {}
        stab: dict[str, str]      = {}

        for key, msg in [
            ("evidence", msgs["evidence_msg"]),
            ("m1",       msgs["m1"]),
            ("m2",       msgs["m2"]),
            ("final",    msgs["m3"]),
        ]:
            outputs = read_all_prompts(msg, ex["question"])
            r, s = majority_vote(outputs, ex["answer"])
            raw[key]  = outputs
            R[key]    = r
            stab[key] = s

        # Retention curve + prediction
        curve_result = compute_v0b_curve({
            "R_evidence": R["evidence"],
            "R_m1":       R["m1"],
            "R_m2":       R["m2"],
            "R_final":    R["final"],
        })
        predicted = curve_result["predicted_fault_handoff"]
        drops     = curve_result["drops"]

        # Baselines
        baselines = run_all_baselines(
            {"m1": msgs["m1"], "m2_faulted": msgs["m2"], "m3": msgs["m3"]},
            seed=42,
        )

        # Correctness
        expected = ex["expected_fault_handoff"]
        correct  = 1 if predicted == expected else 0

        # Corruption second channel
        R_corrupt_m2    = ""
        R_corrupt_final = ""
        if ex["fault_type"] == "corruption" and ex.get("corrupted_answer"):
            ca = ex["corrupted_answer"]
            R_corrupt_m2    = majority_vote(raw["m2"],    ca)[0]
            R_corrupt_final = majority_vote(raw["final"], ca)[0]

        pass_fail = "pass" if correct == 1 else "fail"

        row = {
            "id":                ex_id,
            "fault_type":        ex["fault_type"],
            "fault_agent":       ex["fault_agent"],
            "answer":            ex["answer"],
            "corrupted_answer":  ex.get("corrupted_answer", ""),
            "R_evidence":        R["evidence"],
            "R_m1":              R["m1"],
            "R_m2":              R["m2"],
            "R_final":           R["final"],
            "reader_stability_evidence": stab["evidence"],
            "reader_stability_m1":       stab["m1"],
            "reader_stability_m2":       stab["m2"],
            "reader_stability_final":    stab["final"],
            "predicted_handoff":         predicted,
            "expected_fault_handoff":    expected,
            "correct_localization":      correct,
            "baseline_blame_last":       baselines["blame_last"],
            "baseline_blame_random":     baselines["blame_random"],
            "baseline_blame_longest":    baselines["blame_longest_message"],
            "baseline_blame_shortest":   baselines["blame_shortest_message"],
            "drop_agent1_to_agent2":     drops.get("agent1_to_agent2", 0),
            "drop_agent2_to_agent3":     drops.get("agent2_to_agent3", 0),
            "drop_agent3_final_output":  drops.get("agent3_final_output", 0),
            "R_corrupt_m2":              R_corrupt_m2,
            "R_corrupt_final":           R_corrupt_final,
            "pass_fail":                 pass_fail,
        }
        rows.append(row)

        trace = {
            "id":         ex_id,
            "fault_type": ex["fault_type"],
            "fault_agent": ex["fault_agent"],
            "question":   ex["question"],
            "answer":     ex["answer"],
            "messages":   {
                "evidence_msg": msgs["evidence_msg"],
                "m1_clean":     msgs["m1_clean"],
                "m1":           msgs["m1"],
                "m2_clean":     msgs["m2_clean"],
                "m2":           msgs["m2"],
                "m3":           msgs["m3"],
            },
            "raw_outputs": raw,
            "scores":      row,
        }
        traces.append(trace)

        status = "✓" if correct else "✗"
        print(f"    curve: R_ev={R['evidence']} R_m1={R['m1']} "
              f"R_m2={R['m2']} R_fin={R['final']}")
        print(f"    predicted={predicted}  expected={expected}  {status}")

    # Write outputs
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")

    print(f"\nResults written: {csv_path.name}  traces: {jsonl_path.name}")

    # Gate evaluation
    all_pass, gate = _v0b_gate(rows)
    print("\n=== v0b Gate ===\n")
    print(f"  Retention accuracy       : {gate['retention_accuracy']:.0%}  "
          f"({int(gate['retention_accuracy'] * gate['n_fault'])}/{gate['n_fault']} fault examples)")
    print(f"  vs blame_last            : {gate['baseline_blame_last']:.0%}  "
          f"{'BEATS' if gate['beats_last'] else 'FAILS'}")
    print(f"  vs blame_random          : {gate['baseline_blame_random']:.0%}  "
          f"{'BEATS' if gate['beats_random'] else 'FAILS (need >50%)'}")
    print(f"  vs blame_longest         : {gate['baseline_blame_longest']:.0%}  "
          f"{'BEATS' if gate['beats_longest'] else 'FAILS'}")
    print(f"  vs blame_shortest        : {gate['baseline_blame_shortest']:.0%}  "
          f"{'BEATS' if gate['beats_shortest'] else 'FAILS'}")
    print(f"  Clean FP rate            : {gate['clean_fp_rate']:.0%}  "
          f"({'OK' if gate['low_fp'] else 'FAILS (need ≤20%)'})")
    print(f"\n  v0b: {'PASS' if all_pass else 'FAIL'}")

    return 0 if all_pass else 1


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _JSONL_PATH
    return run(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
