"""
inject_faults.py — apply one controlled fault to the Agent 2 clean message.

The fault spec comes directly from the validated example's schema fields.
The operation is deterministic and surgical: no guessing which fact to touch.

Run directly to inspect m2_clean vs m2_faulted for each fault type:
    python inject_faults.py [path_to_jsonl]
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from schemas import VALID_FAULT_TYPES

_JSONL_PATH = Path(__file__).resolve().parent / "fault_examples_v0a.jsonl"


def inject_fault(m2_clean: dict, example: dict) -> dict:
    """
    Apply the fault specified by example['fault_type'] to m2_clean.
    Returns m2_faulted as a new dict; m2_clean is never mutated.

    Behavior by type:
      clean               — return unchanged copy
      benign_compression  — remove irrelevant_facts from known_facts
      destructive_deletion — remove delete_fact from known_facts
      corruption          — replace corrupt_fact with corrupt_replacement
    """
    ft = example["fault_type"]
    if ft not in VALID_FAULT_TYPES:
        raise ValueError(f"Unknown fault_type: {ft!r}")

    m2 = copy.deepcopy(m2_clean)

    if ft == "clean":
        return m2

    if ft == "benign_compression":
        irrelevant = set(example["irrelevant_facts"])
        m2["known_facts"] = [f for f in m2["known_facts"] if f not in irrelevant]
        return m2

    if ft == "destructive_deletion":
        delete = example["delete_fact"]
        before = len(m2["known_facts"])
        m2["known_facts"] = [f for f in m2["known_facts"] if f != delete]
        if len(m2["known_facts"]) == before:
            raise ValueError(f"delete_fact was not found in known_facts: {delete!r}")
        return m2

    if ft == "corruption":
        corrupt_fact = example["corrupt_fact"]
        replacement = example["corrupt_replacement"]
        replaced = False
        new_facts = []
        for f in m2["known_facts"]:
            if f == corrupt_fact:
                new_facts.append(replacement)
                replaced = True
            else:
                new_facts.append(f)
        if not replaced:
            raise ValueError(f"corrupt_fact was not found in known_facts: {corrupt_fact!r}")
        m2["known_facts"] = new_facts
        return m2

    raise AssertionError(f"unhandled fault_type: {ft!r}")


def inject_into_m1(m1_clean: dict, example: dict) -> dict:
    """
    Apply the fault specified by example to m1_clean (Agent 1's output).
    Only called for fault_agent == 1 examples. Returns m1_faulted as a new
    dict; m1_clean is never mutated.

    Supports destructive_deletion and corruption only — benign_compression
    and clean are not valid Agent-1 fault types in v0b.
    """
    ft = example["fault_type"]
    if ft not in VALID_FAULT_TYPES:
        raise ValueError(f"Unknown fault_type: {ft!r}")

    m1 = copy.deepcopy(m1_clean)

    if ft == "destructive_deletion":
        delete = example["delete_fact"]
        before = len(m1["known_facts"])
        m1["known_facts"] = [f for f in m1["known_facts"] if f != delete]
        if len(m1["known_facts"]) == before:
            raise ValueError(f"delete_fact was not found in m1 known_facts: {delete!r}")
        return m1

    if ft == "corruption":
        corrupt_fact = example["corrupt_fact"]
        replacement = example["corrupt_replacement"]
        replaced = False
        new_facts = []
        for f in m1["known_facts"]:
            if f == corrupt_fact:
                new_facts.append(replacement)
                replaced = True
            else:
                new_facts.append(f)
        if not replaced:
            raise ValueError(f"corrupt_fact was not found in m1 known_facts: {corrupt_fact!r}")
        m1["known_facts"] = new_facts
        return m1

    raise ValueError(f"inject_into_m1 does not support fault_type {ft!r}")


def _print_trace(example: dict, m2_clean: dict, m2_faulted: dict) -> None:
    ft = example["fault_type"]
    print(f"id            : {example['id']}")
    print(f"fault_type    : {ft}")
    print(f"question      : {example['question']}")
    print(f"answer        : {example['answer']}")
    if ft == "destructive_deletion":
        print(f"delete_fact   : {example['delete_fact']!r}")
    if ft == "corruption":
        print(f"corrupt_fact  : {example['corrupt_fact']!r}")
        print(f"replacement   : {example['corrupt_replacement']!r}")
        print(f"corrupted_ans : {example['corrupted_answer']!r}")
    print(f"m2_clean  ({len(m2_clean['known_facts'])} facts):")
    for f in m2_clean["known_facts"]:
        print(f"    {f!r}")
    print(f"m2_faulted({len(m2_faulted['known_facts'])} facts):")
    for f in m2_faulted["known_facts"]:
        print(f"    {f!r}")
    print()


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _JSONL_PATH
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    from load_data import load_and_validate
    from build_messages import build_clean_messages

    try:
        examples = load_and_validate(path)
    except Exception as e:
        print(f"Load/validation error: {e}")
        return 1

    fault_order = ["clean", "benign_compression", "destructive_deletion", "corruption"]
    seen: set[str] = set()
    print("=== inject_faults.py: m2_clean vs m2_faulted per fault type ===\n")
    for ex in examples:
        ft = ex["fault_type"]
        if ft in fault_order and ft not in seen:
            _, m2_clean = build_clean_messages(ex)
            m2_faulted = inject_fault(m2_clean, ex)
            _print_trace(ex, m2_clean, m2_faulted)
            seen.add(ft)
        if seen == set(fault_order):
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
