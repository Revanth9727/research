"""
schemas.py — single source of truth for what a valid v0a example looks like.

Every downstream module assumes fields are present and well-formed, so all
validation happens here, once, up front. A failed check raises SchemaError
with a message naming the example id and the exact problem.
"""

from __future__ import annotations

REQUIRED_FIELDS = {
    "id",
    "evidence",
    "question",
    "answer",
    "corrupted_answer",
    "needed_facts",
    "irrelevant_facts",
    "fault_type",
    "fault_agent",
    "delete_fact",
    "corrupt_fact",
    "corrupt_replacement",
    "expected_fault_handoff",
}

VALID_FAULT_TYPES = {
    "clean",
    "benign_compression",
    "destructive_deletion",
    "corruption",
}

VALID_FAULT_AGENTS = {1, 2}

# Handoff labels used by v0b.
HANDOFF_LABELS = [
    "agent1_to_agent2",
    "agent2_to_agent3",
]


def expected_handoff(fault_type: str, fault_agent: int) -> str:
    """Return the expected_fault_handoff for a given fault_type and fault_agent.

    clean / benign_compression always map to 'none' — no information lost.
    deletion / corruption map to the handoff produced by the faulted agent.
    """
    if fault_type in ("clean", "benign_compression"):
        return "none"
    if fault_agent == 1:
        return "agent1_to_agent2"
    if fault_agent == 2:
        return "agent2_to_agent3"
    raise ValueError(f"Unhandled fault_agent={fault_agent!r} for fault_type={fault_type!r}")


class SchemaError(ValueError):
    """Raised when an example fails validation."""


def _err(example_id, msg):
    return SchemaError(f"[{example_id}] {msg}")


def validate_example(ex: dict) -> None:
    """Validate a single example. Raises SchemaError on the first problem found."""
    ex_id = ex.get("id", "<no id>")

    # 1. field presence (no missing, no unexpected)
    keys = set(ex.keys())
    missing = REQUIRED_FIELDS - keys
    if missing:
        raise _err(ex_id, f"missing fields: {sorted(missing)}")
    extra = keys - REQUIRED_FIELDS
    if extra:
        raise _err(ex_id, f"unexpected fields: {sorted(extra)}")

    # 2. fault_type is known
    ft = ex["fault_type"]
    if ft not in VALID_FAULT_TYPES:
        raise _err(ex_id, f"invalid fault_type: {ft!r}")

    # 3. fault_agent must be a known value
    fa = ex["fault_agent"]
    if fa not in VALID_FAULT_AGENTS:
        raise _err(ex_id, f"invalid fault_agent: {fa!r} (must be 1 or 2)")

    # 4. expected_fault_handoff matches the (fault_type, fault_agent) rule
    want = expected_handoff(ft, fa)
    if ex["expected_fault_handoff"] != want:
        raise _err(
            ex_id,
            f"expected_fault_handoff should be {want!r} for "
            f"fault_type={ft!r} fault_agent={fa}, "
            f"got {ex['expected_fault_handoff']!r}",
        )

    # 5. basic type / non-empty checks
    for list_field in ("evidence", "needed_facts", "irrelevant_facts"):
        if not isinstance(ex[list_field], list):
            raise _err(ex_id, f"{list_field} must be a list")
    if not ex["question"] or not ex["answer"]:
        raise _err(ex_id, "question and answer must be non-empty")
    if len(ex["irrelevant_facts"]) < 1:
        raise _err(ex_id, "must have at least one irrelevant fact")

    # needed + irrelevant should reconstruct evidence
    if set(ex["needed_facts"]) | set(ex["irrelevant_facts"]) != set(ex["evidence"]):
        raise _err(ex_id, "needed_facts + irrelevant_facts do not equal evidence")

    # 6. fault-type-specific requirements
    if ft == "destructive_deletion":
        if not ex["delete_fact"]:
            raise _err(ex_id, "deletion row missing delete_fact")
        if ex["delete_fact"] not in ex["needed_facts"]:
            raise _err(ex_id, "delete_fact not found in needed_facts")
        if ex["corrupt_fact"] or ex["corrupt_replacement"]:
            raise _err(ex_id, "deletion row must not set corruption fields")

    elif ft == "corruption":
        if not ex["corrupt_fact"]:
            raise _err(ex_id, "corruption row missing corrupt_fact")
        if not ex["corrupt_replacement"]:
            raise _err(ex_id, "corruption row missing corrupt_replacement")
        if not ex["corrupted_answer"]:
            raise _err(ex_id, "corruption row missing corrupted_answer")
        if ex["corrupt_fact"] not in ex["needed_facts"]:
            raise _err(ex_id, "corrupt_fact not found in needed_facts")
        if ex["delete_fact"]:
            raise _err(ex_id, "corruption row must not set delete_fact")

    else:  # clean, benign_compression
        if ex["delete_fact"] or ex["corrupt_fact"] or ex["corrupt_replacement"]:
            raise _err(ex_id, f"{ft} row must not set any fault operation fields")


def validate_dataset(examples: list[dict]) -> None:
    """Validate every example and check ids are unique."""
    seen = set()
    for ex in examples:
        validate_example(ex)
        if ex["id"] in seen:
            raise _err(ex["id"], "duplicate id")
        seen.add(ex["id"])
