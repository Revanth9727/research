"""
load_data.py — load the v0a JSONL, validate it, and report a summary.

Run directly:
    python load_data.py [path]

Prints the per-type counts and a PASS/FAIL validation verdict. Any schema
problem is reported with the offending example id and reason.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from schemas import validate_dataset, SchemaError, VALID_FAULT_TYPES

DEFAULT_PATH = Path(__file__).resolve().parent / "fault_examples_v0a.jsonl"


def load_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file into a list of dicts. Reports the line number on parse errors."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")
    examples = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"bad JSON on line {lineno}: {e}") from e
    return examples


def load_and_validate(path: str | Path = DEFAULT_PATH) -> list[dict]:
    """Load and validate; raises on any problem, returns the examples on success."""
    examples = load_jsonl(path)
    validate_dataset(examples)
    return examples


def _print_summary(examples: list[dict], validation_ok: bool) -> None:
    counts = Counter(ex.get("fault_type", "<none>") for ex in examples)
    print(f"Total examples: {len(examples)}")
    for ft in sorted(VALID_FAULT_TYPES):
        print(f"{ft}: {counts.get(ft, 0)}")
    other = set(counts) - VALID_FAULT_TYPES
    for ft in sorted(other):
        print(f"{ft} (unexpected): {counts[ft]}")
    print(f"Validation: {'PASS' if validation_ok else 'FAIL'}")


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else DEFAULT_PATH
    try:
        examples = load_jsonl(path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Load error: {e}")
        return 1

    try:
        validate_dataset(examples)
    except SchemaError as e:
        _print_summary(examples, validation_ok=False)
        print(f"Reason: {e}")
        return 1

    _print_summary(examples, validation_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
