"""
run_v0a.py — v0a detection experiment end-to-end.

Pipeline per example:
  load → build_clean_messages → inject_fault → read (4 conditions, 3 prompts each)
  → majority_vote → compute_v0a_signal → compute_pass_fail → write outputs

Reader conditions per example (12 calls total):
  m2_clean          — primary clean baseline
  m2_faulted        — primary faulted signal
  no_context        — empty message leakage control
  irrelevant_context — another example's facts leakage control

Outputs (written to results/):
  results_v0a.csv
  traces_v0a.jsonl
  run_manifest_v0a_<run_id>.json

Usage:
    python run_v0a.py [path_to_jsonl]
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from build_messages import build_clean_messages, build_m3
from inject_faults import inject_fault
from reader import read_all_prompts, manifest_entry
from retention import majority_vote, compute_v0a_signal, compute_pass_fail, SCORING_VERSION
from scoring import score_answer

_JSONL_PATH = Path(__file__).resolve().parent / "fault_examples_v0a.jsonl"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"

CSV_COLUMNS = [
    "id", "fault_type", "answer", "corrupted_answer",
    "R_correct_clean", "R_correct_faulted",
    "R_correct_no_context", "R_correct_irrelevant_context",
    "R_corrupt_clean", "R_corrupt_faulted",
    "reader_stability_clean", "reader_stability_faulted",
    "memory_leak_flag", "hallucination_flag",
    "detected_drop", "expected_fault_handoff", "pass_fail",
]


def _no_context_message() -> dict:
    return {"known_facts": [], "reasoning_summary": "", "answer_candidate": ""}


def _hallucination_flag(raw_outputs: list[str], gold: str) -> int:
    """
    1 if the reader gives varying non-UNKNOWN answers that all fail to match gold.
    Indicates fabrication rather than honest UNKNOWN responses.
    """
    all_fail = all(score_answer(o, gold) == 0 for o in raw_outputs)
    if not all_fail:
        return 0
    normalized = [o.lower().strip() for o in raw_outputs]
    not_all_unknown = any(n != "unknown" for n in normalized)
    varies = len(set(normalized)) > 1
    return 1 if (not_all_unknown and varies) else 0


def process_example(ex: dict, irrel_msg: dict) -> tuple[dict, dict]:
    """
    Run one example through the full v0a pipeline.

    irrel_msg: m2_clean from a different example, used as irrelevant_context.
    Returns (csv_row dict, trace dict).
    """
    m1, m2_clean = build_clean_messages(ex)
    m2_faulted = inject_fault(m2_clean, ex)
    m3 = build_m3(m2_faulted)
    no_ctx = _no_context_message()
    question = ex["question"]
    gold = ex["answer"]

    # 12 reader calls: 3 prompts × 4 conditions
    raw_clean  = read_all_prompts(m2_clean,  question)
    raw_faulted = read_all_prompts(m2_faulted, question)
    raw_no_ctx = read_all_prompts(no_ctx,     question)
    raw_irrel  = read_all_prompts(irrel_msg,  question)

    R_correct_clean,  stab_clean   = majority_vote(raw_clean,   gold)
    R_correct_faulted, stab_faulted = majority_vote(raw_faulted, gold)
    R_correct_no_ctx, _            = majority_vote(raw_no_ctx,  gold)
    R_correct_irrel,  _            = majority_vote(raw_irrel,   gold)

    # R_corrupt: only for corruption examples
    R_corrupt_clean_val   = ""
    R_corrupt_faulted_val = ""
    if ex["fault_type"] == "corruption":
        corrupt_ans = ex["corrupted_answer"]
        R_corrupt_clean_val,   _ = majority_vote(raw_clean,   corrupt_ans)
        R_corrupt_faulted_val, _ = majority_vote(raw_faulted, corrupt_ans)

    memory_leak  = 1 if R_correct_no_ctx == 1 else 0
    hallucination = _hallucination_flag(raw_clean, gold)
    signal = compute_v0a_signal(R_correct_clean, R_correct_faulted)

    row = {
        "id":                          ex["id"],
        "fault_type":                  ex["fault_type"],
        "answer":                      gold,
        "corrupted_answer":            ex.get("corrupted_answer", ""),
        "R_correct_clean":             R_correct_clean,
        "R_correct_faulted":           R_correct_faulted,
        "R_correct_no_context":        R_correct_no_ctx,
        "R_correct_irrelevant_context": R_correct_irrel,
        "R_corrupt_clean":             R_corrupt_clean_val,
        "R_corrupt_faulted":           R_corrupt_faulted_val,
        "reader_stability_clean":      stab_clean,
        "reader_stability_faulted":    stab_faulted,
        "memory_leak_flag":            memory_leak,
        "hallucination_flag":          hallucination,
        "detected_drop":               signal["detected_drop"],
        "expected_fault_handoff":      ex["expected_fault_handoff"],
        "pass_fail":                   "",
    }
    row["pass_fail"] = compute_pass_fail(row)

    trace = {
        "id":         ex["id"],
        "fault_type": ex["fault_type"],
        "question":   question,
        "answer":     gold,
        "messages": {
            "m1":         m1,
            "m2_clean":   m2_clean,
            "m2_faulted": m2_faulted,
            "m3":         m3,
        },
        "raw_outputs": {
            "m2_clean":          raw_clean,
            "m2_faulted":        raw_faulted,
            "no_context":        raw_no_ctx,
            "irrelevant_context": raw_irrel,
        },
        "scores": {
            "R_correct_clean":             R_correct_clean,
            "R_correct_faulted":           R_correct_faulted,
            "R_correct_no_context":        R_correct_no_ctx,
            "R_correct_irrelevant_context": R_correct_irrel,
            "R_corrupt_clean":             R_corrupt_clean_val,
            "R_corrupt_faulted":           R_corrupt_faulted_val,
            "memory_leak_flag":            memory_leak,
            "hallucination_flag":          hallucination,
            "detected_drop":               signal["detected_drop"],
            "pass_fail":                   row["pass_fail"],
        },
    }
    return row, trace


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _JSONL_PATH

    from load_data import load_and_validate
    try:
        examples = load_and_validate(path)
    except Exception as e:
        print(f"Load error: {e}")
        return 1

    _RESULTS_DIR.mkdir(exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]

    # Write manifest before the run starts
    reader_config = manifest_entry()
    manifest = {
        **reader_config,
        "dataset_file":   str(path),
        "dataset_hash":   dataset_hash,
        "scoring_version": SCORING_VERSION,
        "run_id":         run_id,
        "timestamp":      datetime.now().isoformat(),
    }
    manifest_path = _RESULTS_DIR / f"run_manifest_v0a_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest : {manifest_path}")

    # Pre-build all m2_clean messages for the irrelevant_context condition.
    # Example i uses example (i+10) % N — opposite half of the dataset,
    # so clean/benign examples get deletion/corruption facts and vice versa.
    all_m2_clean = [build_clean_messages(ex)[1] for ex in examples]

    rows: list[dict] = []
    traces: list[dict] = []

    print(f"\nRunning v0a  ({len(examples)} examples)  run_id={run_id}\n")

    for i, ex in enumerate(examples):
        irrel_msg = all_m2_clean[(i + 10) % len(examples)]
        print(
            f"  [{i+1:02d}/{len(examples)}] {ex['id']} ({ex['fault_type']:<22}) ...",
            end=" ", flush=True,
        )
        row, trace = process_example(ex, irrel_msg)
        rows.append(row)
        traces.append(trace)
        print(
            f"{row['pass_fail'].upper():<5}  "
            f"R_cc={row['R_correct_clean']}  R_cf={row['R_correct_faulted']}"
            + (f"  R_rf={row['R_corrupt_faulted']}" if ex["fault_type"] == "corruption" else "")
        )

    # Write CSV
    csv_path = _RESULTS_DIR / "results_v0a.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV     : {csv_path}")

    # Write traces
    traces_path = _RESULTS_DIR / "traces_v0a.jsonl"
    with open(traces_path, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")
    print(f"Traces  : {traces_path}")

    # Final verdict
    n_pass = sum(1 for r in rows if r["pass_fail"] == "pass")
    print(f"\nResult  : {n_pass}/{len(rows)} examples pass the v0a gate")
    if n_pass == len(rows):
        print("v0a PASS — signal confirmed. Proceed to v0b.")
    else:
        fails = [r["id"] for r in rows if r["pass_fail"] == "fail"]
        print(f"v0a FAIL — {len(fails)} failed: {fails}")
        print("Run:  python analyze_results.py  for failure diagnosis.")

    return 0 if n_pass == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
