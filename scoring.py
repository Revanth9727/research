"""
scoring.py — convert a raw reader output to a binary score against a target answer.

Signature:
    score_answer(reader_output, target_answer) -> 1 or 0

The target must always be passed explicitly — never hardcoded to gold:
    R_correct = score_answer(output, example["answer"])
    R_corrupt = score_answer(output, example["corrupted_answer"])

Normalization: lowercase, strip edge punctuation and whitespace, collapse
internal whitespace. Numbers and units are preserved intact, so "80 years"
and "45 years" remain distinct.

Run directly to verify normalization and scoring behavior:
    python scoring.py
"""

from __future__ import annotations

import re
import string


def _normalize(text: str) -> str:
    """Lowercase, strip edge punctuation and whitespace, collapse internal whitespace."""
    text = text.lower().strip()
    text = text.strip(string.punctuation)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_answer(reader_output: str, target_answer: str) -> int:
    """
    Return 1 if reader_output recovers target_answer after normalization, else 0.

    A reader output of "UNKNOWN" (or empty) always scores 0 against any
    real target because _normalize("UNKNOWN") == "unknown", which will not
    match any well-formed answer.
    """
    if not reader_output or not target_answer:
        return 0
    return int(_normalize(reader_output) == _normalize(target_answer))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_TESTS: list[tuple[str, str, int, str]] = [
    ("80 years",       "80 years",       1, "exact match"),
    ("80 years",       "45 years",       0, "different value — units preserved"),
    ("  1985.",        "1985",           1, "edge whitespace + trailing period"),
    ("UNKNOWN",        "1985",           0, "UNKNOWN never recovers"),
    ("Brellia",        "brellia",        1, "case insensitive"),
    ("Brellia",        "Brellia",        1, "same case"),
    ("Corin Society",  "corin society",  1, "multi-word case normalisation"),
    ("",               "1985",           0, "empty reader output"),
    ("1985",           "",               0, "empty target"),
    ("Pellor",         "Pellor",         1, "single-word exact"),
    ("Pellor",         "Draymoor",       0, "different single word"),
    ("  Wexler  ",     "Wexler",         1, "surrounding whitespace"),
    ("Merrow Academy", "Merrow Academy", 1, "multi-word exact"),
    ("Merrow Academy", "Merrow",         0, "partial match does not score"),
]


def _run_tests() -> None:
    passed = 0
    failed = 0
    for reader_out, target, expected, label in _TESTS:
        result = score_answer(reader_out, target)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        passed += ok
        failed += not ok
        print(f"  [{status}] {label}")
        if not ok:
            print(f"         reader_output={reader_out!r}  target={target!r}")
            print(f"         expected={expected}  got={result}")
    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    print("=== scoring.py tests ===\n")
    _run_tests()
