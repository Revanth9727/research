"""
scoring.py — convert a raw reader output to a binary score against a target answer.

Signature:
    score_answer(reader_output, target_answer) -> 1 or 0

The target must always be passed explicitly — never hardcoded to gold:
    R_correct = score_answer(output, example["answer"])
    R_corrupt = score_answer(output, example["corrupted_answer"])

Normalization (v2_bridge): lowercase, strip edge punctuation and whitespace,
collapse internal whitespace, strip one leading article (the/a/an).
Numbers and units are preserved intact, so "80 years" and "45 years" remain distinct.

score_answer uses a commitment check (v2_bridge): the reader output scores 1
if it contains the target as a whole-phrase word-boundary match AND no negation
cue immediately precedes the match. This handles natural sentence outputs without
introducing any LLM-based judge. See scoring spec in docs/implementation_plan.md.

Run directly to verify normalization and scoring behavior:
    python scoring.py
"""

from __future__ import annotations

import re
import string

SCORING_VERSION = "v2_bridge"

_NEGATION_CUES = (
    "not", "isn't", "wasn't", "weren't", "n't", "rather than", "instead of", "no longer",
)

_AMBIGUITY_CUES = re.compile(r"\b(or|either|possibly|maybe|perhaps|might be)\b")

# Words that indicate the output is a sentence/clause rather than a bare compound entity.
# If none of these appear in the extra words (output minus target), the output is
# treated as a named-entity extension (e.g. 'Merrow Academy' vs target 'Merrow') → 0.
_SENTENCE_MARKERS = frozenset({
    "is", "was", "are", "were", "has", "have", "had", "been",
    "in", "at", "of", "from", "to", "for", "with", "by", "on",
    "that", "which", "who", "when", "where", "it", "its",
    "and", "but", "founded", "formed", "created", "built",
    "established", "called", "known", "answer", "the",
})

_LEADING_ARTICLE = re.compile(r"^(the|an?)\s+")


def _normalize(text: str) -> str:
    """Lowercase, strip edge punctuation/whitespace, collapse whitespace, strip leading article."""
    text = text.lower().strip()
    text = text.strip(string.punctuation)
    text = re.sub(r"\s+", " ", text).strip()
    text = _LEADING_ARTICLE.sub("", text)
    return text


def _negation_near(output_norm: str, match: re.Match) -> bool:
    """
    Return True if a negation cue appears immediately before the matched span.
    'Immediately before' means within the 60 characters preceding the match start.
    """
    window = output_norm[max(0, match.start() - 60): match.start()]
    for cue in _NEGATION_CUES:
        if re.search(r"\b" + re.escape(cue) + r"\b", window):
            return True
    return False


def _ambiguity_near(output_norm: str, match: re.Match) -> bool:
    """
    Return True if a disjunction marker appears immediately after the matched span,
    indicating the output presents the target as one of several options rather than
    a committed answer. Window: 15 characters after the match end.
    """
    window = output_norm[match.end(): match.end() + 15]
    return bool(_AMBIGUITY_CUES.search(window))


def score_answer(reader_output: str, target_answer: str) -> int:
    """
    Return 1 if reader_output commits to target_answer, else 0.

    Logic (v2_bridge commitment check):
      1. Normalize both sides.
      2. Empty output or "unknown" → 0.
      3. Exact normalized match → 1.
      4. Word-boundary search for target phrase inside output.
         - If found and no negation cue precedes it → 1.
         - If found but negation present → 0.
      5. Otherwise → 0.

    No LLM calls; fully deterministic string logic.
    """
    if not reader_output or not target_answer:
        return 0

    out_n = _normalize(reader_output)
    tgt_n = _normalize(target_answer)

    if not out_n or out_n == "unknown":
        return 0

    if out_n == tgt_n:
        return 1

    # Word-boundary search: target must appear as a complete phrase, not inside
    # a longer token. re.escape handles multi-word targets correctly.
    pattern = r"(?<!\w)" + re.escape(tgt_n) + r"(?!\w)"
    m = re.search(pattern, out_n)
    if m is None:
        return 0

    if _negation_near(out_n, m):
        return 0

    if _ambiguity_near(out_n, m):
        return 0

    # Compound-entity guard: if every word in the output beyond the target words
    # is a content/noun word (no sentence-context word present), the output is
    # committing to a longer entity, not to the target alone.
    tgt_words = set(re.split(r"\W+", tgt_n)) - {""}
    out_words = set(re.split(r"\W+", out_n)) - {""}
    extra = out_words - tgt_words
    if extra and not (extra & _SENTENCE_MARKERS):
        return 0

    return 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_TESTS: list[tuple[str, str, int, str]] = [
    # --- original 14 cases ---
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
    # --- new v2_bridge cases ---
    ("The Sarn Guild was formed in 1990.", "1990",         1, "answer in sentence"),
    ("The Corin Society",                 "Corin Society", 1, "leading article stripped"),
    ("It's not 1990, it's 1972.",         "1990",          0, "negation trap"),
    ("The answer is 1972.",               "1990",          0, "different definite answer"),
    # Ambiguous output is NOT a clean recovery; the bridge requires a clear commit.
    ("1990 or 1991, hard to say",         "1990",          0, "ambiguous — not a clean commit"),
    ("11990",                             "1990",          0, "word-boundary: must not match inside larger token"),
    ("1985",                              "1985",          1, "bare exact still works"),
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
    print(f"=== scoring.py tests ({SCORING_VERSION}) ===\n")
    _run_tests()
