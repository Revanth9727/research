"""
build_messages.py — deterministic agent message builder for v0a.

Turns one validated example into the structured agent messages without
any LLM calls. All messages use the format:
    {"known_facts": [...], "reasoning_summary": "", "answer_candidate": ""}

Run directly to inspect one trace per fault type:
    python build_messages.py [path_to_jsonl]
"""

from __future__ import annotations

import sys
from pathlib import Path

_JSONL_PATH = Path(__file__).resolve().parent / "fault_examples_v0a.jsonl"


def build_m1(example: dict) -> dict:
    """Agent 1 (Retriever): populate known_facts with all evidence facts."""
    return {
        "known_facts": list(example["evidence"]),
        "reasoning_summary": "",
        "answer_candidate": "",
    }


def build_m2_clean(m1: dict) -> dict:
    """Agent 2 (Reasoner): pass known_facts through unchanged. No reasoning in v0a."""
    return {
        "known_facts": list(m1["known_facts"]),
        "reasoning_summary": "",
        "answer_candidate": "",
    }


def build_m3(m2: dict) -> dict:
    """
    Agent 3 (Answerer): build from the (possibly faulted) m2 it receives.

    Leakage rule: this function must only be called with m2_faulted, never
    with the gold answer, original evidence, needed_facts, delete_fact, or
    corrupt_replacement. In v0a, calling this is optional — R(m2_clean) vs
    R(m2_faulted) is sufficient for detection without scoring m3.
    """
    return {
        "known_facts": list(m2["known_facts"]),
        "reasoning_summary": "",
        "answer_candidate": "",
    }


def build_clean_messages(example: dict) -> tuple[dict, dict]:
    """
    Build m1 and m2_clean for one example.

    Returns (m1, m2_clean). m3 is not built here — it requires the faulted
    m2. Call build_m3(m2_faulted) after inject_faults.inject_fault().
    """
    m1 = build_m1(example)
    m2_clean = build_m2_clean(m1)
    return m1, m2_clean


def build_evidence_message(example: dict) -> dict:
    """
    Build the evidence message — the curve's R(evidence) starting point.
    Contains all evidence facts exactly as given, before any agent touches them.
    """
    return {
        "known_facts": list(example["evidence"]),
        "reasoning_summary": "",
        "answer_candidate": "",
    }


def build_v0b_messages(example: dict) -> dict:
    """
    Build all messages needed for the v0b retention curve for one example.

    Fault routing:
      fault_agent == 1 → inject into m1; m2 and m3 carry the fault forward.
      fault_agent == 2 → m1 is clean; inject into m2; m3 carries forward.
      clean / benign_compression → no injection at any step.

    Returns a dict with keys:
      evidence_msg  — raw evidence (curve start)
      m1            — Agent 1 output (possibly faulted)
      m1_clean      — always-clean m1 (for traces)
      m2            — Agent 2 output (possibly faulted)
      m2_clean      — always-clean m2 (for traces)
      m3            — Agent 3 output built from the post-fault m2
    """
    from inject_faults import inject_fault, inject_into_m1

    fa = example["fault_agent"]  # may be None for clean controls
    ft = example["fault_type"]

    evidence_msg = build_evidence_message(example)
    m1_clean = build_m1(example)

    if fa == 1 and ft not in ("clean", "benign_compression"):
        m1 = inject_into_m1(m1_clean, example)
    else:
        m1 = m1_clean

    m2_clean = build_m2_clean(m1)

    if fa == 2 and ft not in ("clean", "benign_compression"):
        m2 = inject_fault(m2_clean, example)
    else:
        m2 = m2_clean

    m3 = build_m3(m2)

    return {
        "evidence_msg": evidence_msg,
        "m1":           m1,
        "m1_clean":     m1_clean,
        "m2":           m2,
        "m2_clean":     m2_clean,
        "m3":           m3,
    }


def _print_trace(example: dict) -> None:
    m1, m2_clean = build_clean_messages(example)
    print(f"id          : {example['id']}")
    print(f"fault_type  : {example['fault_type']}")
    print(f"question    : {example['question']}")
    print(f"answer      : {example['answer']}")
    print(f"m1  known_facts ({len(m1['known_facts'])} facts):")
    for f in m1["known_facts"]:
        print(f"    {f!r}")
    print(f"m2_clean known_facts ({len(m2_clean['known_facts'])} facts):")
    for f in m2_clean["known_facts"]:
        print(f"    {f!r}")
    print()


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _JSONL_PATH
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    from load_data import load_and_validate
    try:
        examples = load_and_validate(path)
    except Exception as e:
        print(f"Load/validation error: {e}")
        return 1

    fault_order = ["clean", "benign_compression", "destructive_deletion", "corruption"]
    seen: set[str] = set()
    print("=== build_messages.py: one trace per fault type ===\n")
    for ex in examples:
        ft = ex["fault_type"]
        if ft in fault_order and ft not in seen:
            _print_trace(ex)
            seen.add(ft)
        if seen == set(fault_order):
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
