"""
analyze_v0b.py — read results_v0b.csv and print the v0b analysis.

Outputs:
  - Per-agent localization accuracy table
  - Baseline comparison table (retention vs all four baselines)
  - v0b gate verdict (4 criteria)
  - Failure list with diagnosis tags

Usage:
    python analyze_v0b.py [path_to_csv]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

_DEFAULT_CSV = Path(__file__).resolve().parent / "results" / "results_v0b.csv"

_INT_COLS = {
    "fault_agent", "R_evidence", "R_m1", "R_m2", "R_final",
    "correct_localization",
    "drop_agent1_to_agent2", "drop_agent2_to_agent3", "drop_agent3_final_output",
}

_INT_OR_EMPTY = {"R_corrupt_m2", "R_corrupt_final"}


def _load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for col in _INT_COLS:
                if col in row and row[col] != "":
                    row[col] = int(row[col])
            for col in _INT_OR_EMPTY:
                if col in row and row[col] != "":
                    row[col] = int(row[col])
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------

def _retention_acc(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(r["correct_localization"] for r in rows) / len(rows)


def _baseline_acc(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    correct = sum(1 for r in rows if r[key] == r["expected_fault_handoff"])
    return correct / len(rows)


# ---------------------------------------------------------------------------
# Print sections
# ---------------------------------------------------------------------------

def print_localization_table(fault_rows: list[dict]) -> None:
    print("=== v0b Localization Accuracy (fault examples only) ===\n")
    by_agent: dict[int, list] = defaultdict(list)
    for r in fault_rows:
        by_agent[r["fault_agent"]].append(r)

    col_w = [12, 10, 8, 8]
    header = (
        f"{'Fault agent':<{col_w[0]}}"
        f"{'Fault types':<{col_w[1]}}"
        f"{'Correct':>{col_w[2]}}"
        f"{'Total':>{col_w[3]}}"
    )
    print(header)
    print("-" * sum(col_w))

    for agent in sorted(by_agent):
        rows = by_agent[agent]
        correct = sum(r["correct_localization"] for r in rows)
        ft_set = sorted({r["fault_type"] for r in rows})
        print(
            f"{'Agent ' + str(agent):<{col_w[0]}}"
            f"{', '.join(ft_set):<{col_w[1]}}"
            f"{correct:>{col_w[2]}}"
            f"{len(rows):>{col_w[3]}}"
        )

    total_correct = sum(r["correct_localization"] for r in fault_rows)
    print(f"\nOverall: {total_correct}/{len(fault_rows)}  "
          f"({total_correct / len(fault_rows):.0%})")


def print_baseline_comparison(fault_rows: list[dict]) -> None:
    print("\n=== Baseline Comparison (fault examples) ===\n")
    n = len(fault_rows)
    ret_acc = _retention_acc(fault_rows)

    baselines = [
        ("Retention (ours)", ret_acc, None),
        ("blame_last",       _baseline_acc(fault_rows, "baseline_blame_last"),     "baseline_blame_last"),
        ("blame_random",     _baseline_acc(fault_rows, "baseline_blame_random"),   "baseline_blame_random"),
        ("blame_longest",    _baseline_acc(fault_rows, "baseline_blame_longest"),  "baseline_blame_longest"),
        ("blame_shortest",   _baseline_acc(fault_rows, "baseline_blame_shortest"), "baseline_blame_shortest"),
    ]

    col_w = [22, 10, 8]
    header = (
        f"{'Method':<{col_w[0]}}"
        f"{'Accuracy':>{col_w[1]}}"
        f"{'Correct':>{col_w[2]}}"
    )
    print(header)
    print("-" * sum(col_w))

    for name, acc, _ in baselines:
        correct = int(round(acc * n))
        marker = " ←" if name == "Retention (ours)" else ""
        print(f"{name:<{col_w[0]}}{acc:>{col_w[1]}.0%}{correct:>{col_w[2]}}{marker}")


def print_clean_fp(clean_rows: list[dict]) -> None:
    if not clean_rows:
        return
    fp = sum(1 for r in clean_rows if r["predicted_handoff"] != "none")
    rate = fp / len(clean_rows)
    print(f"\n=== Clean-Control False Positives ===\n")
    print(f"  FP (method predicted a location on a clean example): {fp}/{len(clean_rows)}  ({rate:.0%})")
    if fp:
        for r in clean_rows:
            if r["predicted_handoff"] != "none":
                print(f"    {r['id']:<12} predicted={r['predicted_handoff']}")


def print_gate_verdict(fault_rows: list[dict], clean_rows: list[dict]) -> None:
    print("\n=== v0b Gate Verdict ===\n")
    n = len(fault_rows)
    n_clean = len(clean_rows)

    ret_acc     = _retention_acc(fault_rows)
    bl_last_acc = _baseline_acc(fault_rows, "baseline_blame_last")
    bl_long_acc = _baseline_acc(fault_rows, "baseline_blame_longest")
    bl_shor_acc = _baseline_acc(fault_rows, "baseline_blame_shortest")

    fp = sum(1 for r in clean_rows if r["predicted_handoff"] != "none")
    fp_rate = fp / n_clean if n_clean else 0.0

    beats_random   = ret_acc > 0.5
    beats_last     = ret_acc > bl_last_acc
    beats_longest  = ret_acc > bl_long_acc
    beats_shortest = ret_acc > bl_shor_acc
    low_fp         = fp_rate <= 0.20

    def _line(label, result, detail=""):
        mark = "PASS" if result else "FAIL"
        print(f"  [{mark}] {label}{detail}")

    _line(f"Beats random (>{50}%)",
          beats_random,
          f"  retention={ret_acc:.0%}")
    _line("Beats blame_last",
          beats_last,
          f"  retention={ret_acc:.0%} vs last={bl_last_acc:.0%}")
    _line("Beats blame_longest",
          beats_longest,
          f"  retention={ret_acc:.0%} vs longest={bl_long_acc:.0%}")
    _line("Beats blame_shortest",
          beats_shortest,
          f"  retention={ret_acc:.0%} vs shortest={bl_shor_acc:.0%}")
    _line(f"Clean FP rate ≤20%",
          low_fp,
          f"  {fp}/{n_clean} = {fp_rate:.0%}")

    all_pass = all([beats_random, beats_last, beats_longest, beats_shortest, low_fp])
    print(f"\n  v0b: {'PASS ✓' if all_pass else 'FAIL ✗'}")


def print_failures(rows: list[dict]) -> None:
    failed = [r for r in rows if r["pass_fail"] == "fail"]
    if not failed:
        print("\n=== Failures ===\n  None — all examples pass.\n")
        return
    print(f"\n=== Failures ({len(failed)}) ===\n")
    for r in failed:
        tag = _tag_failure(r)
        print(
            f"  {r['id']:<12} agent={r['fault_agent']}  ({r['fault_type']:<22}) [{tag}]"
            f"  curve={r['R_evidence']}→{r['R_m1']}→{r['R_m2']}→{r['R_final']}"
            f"  predicted={r['predicted_handoff']}"
            f"  expected={r['expected_fault_handoff']}"
        )


def _tag_failure(row: dict) -> str:
    if row["R_evidence"] == 0:
        return "weak_reader"
    if row["expected_fault_handoff"] == "none" and row["predicted_handoff"] != "none":
        return "false_positive"
    if row["expected_fault_handoff"] != "none" and row["R_m1"] == 0 and row["fault_agent"] == 1:
        if row["predicted_handoff"] != row["expected_fault_handoff"]:
            return "wrong_agent"
    return "wrong_agent"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_CSV
    if not path.exists():
        print(f"File not found: {path}")
        print("Run  python run_v0b.py  first to generate results.")
        return 1

    rows = _load_csv(path)
    fault_rows = [r for r in rows if r["expected_fault_handoff"] != "none"]
    clean_rows = [r for r in rows if r["expected_fault_handoff"] == "none"]

    print_localization_table(fault_rows)
    print_baseline_comparison(fault_rows)
    print_clean_fp(clean_rows)
    print_gate_verdict(fault_rows, clean_rows)
    print_failures(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
