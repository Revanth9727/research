"""
analyze_results.py — read results_v0a.csv and print the v0a success table.

Outputs:
  - Per-fault-type pass/fail table (v0a success table)
  - False-positive rate for benign_compression
  - False-negative rate for destructive_deletion
  - Corruption separation check (R_corrupt_faulted rises where expected)
  - Failure list with diagnosis tags

Failure tags:
  weak_reader   — reader failed on m2_clean; can't score anything
  bad_injection — no-op or over-aggressive fault caused unexpected drop/no-drop
  real_weakness — signal genuinely failed to detect or distinguish the fault

Usage:
    python analyze_results.py [path_to_csv]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

_DEFAULT_CSV = Path(__file__).resolve().parent / "results" / "results_v0a.csv"

_FAULT_ORDER = ["clean", "benign_compression", "destructive_deletion", "corruption"]

_INT_COLS = {
    "R_correct_clean", "R_correct_faulted",
    "R_correct_no_context", "R_correct_irrelevant_context",
    "memory_leak_flag", "hallucination_flag", "detected_drop",
}

_INT_OR_EMPTY = {"R_corrupt_clean", "R_corrupt_faulted"}

_EXPECTED_SIGNAL = {
    "clean":                "R_cc=1, R_cf=1",
    "benign_compression":   "R_cc=1, R_cf=1",
    "destructive_deletion": "R_cc=1, R_cf=0",
    "corruption":           "R_cc=1, R_cf=0, R_rf=1",
}


def _load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for col in _INT_COLS:
                if col in row:
                    row[col] = int(row[col])
            for col in _INT_OR_EMPTY:
                if col in row and row[col] != "":
                    row[col] = int(row[col])
            rows.append(row)
    return rows


def tag_failure(row: dict) -> str:
    """Assign a single diagnosis tag to a failed example."""
    ft   = row["fault_type"]
    R_cc = row["R_correct_clean"]
    R_cf = row["R_correct_faulted"]

    if R_cc == 0:
        return "weak_reader"

    if ft in ("clean", "benign_compression") and R_cf == 0:
        return "bad_injection"

    if ft == "destructive_deletion" and R_cf == 1:
        return "real_weakness"

    if ft == "corruption":
        R_rf = row.get("R_corrupt_faulted", "")
        if R_cf == 1:
            return "real_weakness"
        if R_rf == "" or R_rf == 0:
            return "real_weakness"

    return "real_weakness"


def print_success_table(by_ft: dict) -> None:
    print("=== v0a Success Table ===\n")
    col_w = [24, 30, 6, 6]
    header = (
        f"{'Fault type':<{col_w[0]}}"
        f"{'Expected signal':<{col_w[1]}}"
        f"{'Pass':>{col_w[2]}}"
        f"{'Total':>{col_w[3]}}"
    )
    print(header)
    print("-" * sum(col_w))
    for ft in _FAULT_ORDER:
        rows = by_ft.get(ft, [])
        n_pass = sum(1 for r in rows if r["pass_fail"] == "pass")
        sig = _EXPECTED_SIGNAL.get(ft, "?")
        print(
            f"{ft:<{col_w[0]}}"
            f"{sig:<{col_w[1]}}"
            f"{n_pass:>{col_w[2]}}"
            f"{len(rows):>{col_w[3]}}"
        )
    all_rows = [r for rows in by_ft.values() for r in rows]
    n_pass = sum(1 for r in all_rows if r["pass_fail"] == "pass")
    print(f"\nOverall: {n_pass}/{len(all_rows)} pass")


def print_diagnostic_stats(by_ft: dict) -> None:
    print("\n=== Diagnostic Stats ===\n")

    benign = by_ft.get("benign_compression", [])
    fp = sum(1 for r in benign if r["R_correct_faulted"] == 0)
    print(f"Benign compression  false-positive rate : {fp}/{len(benign)}"
          + (f"  ({fp/len(benign):.0%})" if benign else ""))

    deletion = by_ft.get("destructive_deletion", [])
    fn = sum(1 for r in deletion if r["R_correct_faulted"] == 1)
    print(f"Destructive deletion false-negative rate: {fn}/{len(deletion)}"
          + (f"  ({fn/len(deletion):.0%})" if deletion else ""))

    corruption = by_ft.get("corruption", [])
    sep = sum(1 for r in corruption if r.get("R_corrupt_faulted") == 1)
    print(f"Corruption separation (R_rf=1 where expected): {sep}/{len(corruption)}"
          + (f"  ({sep/len(corruption):.0%})" if corruption else ""))

    all_rows = [r for rows in by_ft.values() for r in rows]
    leaks   = sum(1 for r in all_rows if r["memory_leak_flag"] == 1)
    halluc  = sum(1 for r in all_rows if r["hallucination_flag"] == 1)
    print(f"Memory leak flags   : {leaks}/{len(all_rows)}")
    print(f"Hallucination flags : {halluc}/{len(all_rows)}")


def print_failures(rows: list[dict]) -> None:
    failed = [r for r in rows if r["pass_fail"] == "fail"]
    if not failed:
        print("\n=== Failures ===\n  None — all examples pass.\n")
        return
    print(f"\n=== Failures ({len(failed)}) ===\n")
    for r in failed:
        tag = tag_failure(r)
        corruption_extra = (
            f"  R_rf={r['R_corrupt_faulted']}"
            if r["fault_type"] == "corruption" else ""
        )
        print(
            f"  {r['id']:<10} ({r['fault_type']:<22}) [{tag}]"
            f"  R_cc={r['R_correct_clean']}"
            f"  R_cf={r['R_correct_faulted']}"
            + corruption_extra
        )


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_CSV
    if not path.exists():
        print(f"File not found: {path}")
        print("Run  python run_v0a.py  first to generate results.")
        return 1

    rows = _load_csv(path)
    by_ft: dict[str, list] = defaultdict(list)
    for r in rows:
        by_ft[r["fault_type"]].append(r)

    print_success_table(by_ft)
    print_diagnostic_stats(by_ft)
    print_failures(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
