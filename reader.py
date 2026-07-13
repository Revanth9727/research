"""
reader.py — frozen reader model for v0a.

Given a message dict and a question, asks the frozen model to recover the
answer from the message alone. Returns the raw answer string (or UNKNOWN).
Scoring against a target answer is handled separately in scoring.py.

Three frozen prompt variants are defined here. Majority-vote scoring
(R = 1 if at least 2/3 prompts recover the target) is handled by the caller
in run_v0a.py.

Model and decoding settings are fixed and exported via manifest_entry()
for inclusion in results/run_manifest_v0a_<run_id>.json.

Run directly to smoke-test model loading on one dataset example:
    python reader.py [path_to_jsonl]
"""

from __future__ import annotations

import sys
from pathlib import Path

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
PROMPT_VERSION = "v1"

# Three frozen prompt variants for majority-vote scoring.
# All share the same {message} and {question} substitution slots.
PROMPTS: list[str] = [
    (
        "Given only the message below, answer the question. "
        "If the answer is not recoverable, output UNKNOWN.\n\n"
        "Message:\n{message}\n\nQuestion: {question}\n\nAnswer:"
    ),
    (
        "Use only the provided message. Do not use outside knowledge. "
        "Return only the answer, or UNKNOWN if the answer is not stated "
        "or inferable.\n\n"
        "Message:\n{message}\n\nQuestion: {question}\n\nAnswer:"
    ),
    (
        "Can the question be answered from this message alone? "
        "If yes, return the answer. If no, return UNKNOWN.\n\n"
        "Message:\n{message}\n\nQuestion: {question}\n\nAnswer:"
    ),
]

DECODING_CONFIG: dict = {
    "max_new_tokens": 50,
    "do_sample": False,
}

_pipeline = None


def _get_pipeline():
    """Load the Qwen2.5 pipeline once; reuse on all subsequent calls."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline
        _pipeline = pipeline(
            "text-generation",
            model=MODEL_NAME,
            device_map="auto",
            dtype="auto",
        )
    return _pipeline


def _format_message(message: dict) -> str:
    """
    Format a message dict as readable text for insertion into a reader prompt.

    For v0a all messages have empty reasoning_summary and answer_candidate,
    so only known_facts is rendered. Non-empty fields are included automatically,
    making this forward-compatible with v0b hosted-agent messages.
    """
    facts = message.get("known_facts", [])
    reasoning = message.get("reasoning_summary", "")
    answer_candidate = message.get("answer_candidate", "")

    parts = []
    if facts:
        parts.append("Facts:\n" + "\n".join(f"- {f}" for f in facts))
    if reasoning:
        parts.append(f"Reasoning: {reasoning}")
    if answer_candidate:
        parts.append(f"Answer candidate: {answer_candidate}")

    return "\n".join(parts) if parts else "No information provided."


def read_message(message: dict, question: str, prompt_idx: int = 0) -> str:
    """
    Run one reader prompt. Returns the raw answer string, or UNKNOWN.

    prompt_idx: 0, 1, or 2 — which of the three frozen prompt variants to use.
    """
    if prompt_idx not in range(len(PROMPTS)):
        raise ValueError(f"prompt_idx must be 0, 1, or 2; got {prompt_idx}")

    pipe = _get_pipeline()
    message_text = _format_message(message)
    prompt = PROMPTS[prompt_idx].format(message=message_text, question=question)

    output = pipe(
        [{"role": "user", "content": prompt}],
        **DECODING_CONFIG,
    )

    generated = output[0]["generated_text"]
    if isinstance(generated, list):
        raw = generated[-1]["content"].strip()
    else:
        raw = str(generated).strip()

    return raw if raw else "UNKNOWN"


def read_all_prompts(message: dict, question: str) -> list[str]:
    """
    Run all three prompt variants. Returns a list of three raw answer strings.

    Used by run_v0a.py for majority-vote scoring:
        outputs = read_all_prompts(message, question)
        scores  = [score_answer(o, target) for o in outputs]
        R       = 1 if sum(scores) >= 2 else 0
        reader_stability = f"{sum(scores)}/{len(scores)}"
    """
    return [read_message(message, question, i) for i in range(len(PROMPTS))]


def manifest_entry() -> dict:
    """Return the reader configuration for inclusion in run_manifest.json."""
    return {
        "reader_model": MODEL_NAME,
        "reader_prompt_version": PROMPT_VERSION,
        "decoding_config": DECODING_CONFIG,
        "num_prompts": len(PROMPTS),
    }


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent / "fault_examples_v0a.jsonl"

    from load_data import load_and_validate
    from build_messages import build_clean_messages
    from inject_faults import inject_fault

    try:
        examples = load_and_validate(path)
    except Exception as e:
        print(f"Load error: {e}")
        return 1

    # Smoke-test on one clean example and one deletion example
    target_types = {"clean", "destructive_deletion"}
    chosen: dict[str, dict] = {}
    for ex in examples:
        ft = ex["fault_type"]
        if ft in target_types and ft not in chosen:
            chosen[ft] = ex
        if len(chosen) == len(target_types):
            break

    print(f"=== reader.py smoke test ===")
    print(f"model   : {MODEL_NAME}")
    print(f"prompts : {len(PROMPTS)} variants (majority vote: 2/3)\n")

    for ft, ex in chosen.items():
        _, m2_clean = build_clean_messages(ex)
        m2_faulted = inject_fault(m2_clean, ex)
        message = m2_clean if ft == "clean" else m2_faulted

        print(f"--- {ex['id']} ({ft}) ---")
        print(f"question       : {ex['question']}")
        print(f"expected answer: {ex['answer']}")
        print(f"known_facts    : {message['known_facts']}")
        print("reader outputs (3 prompts):")
        outputs = read_all_prompts(message, ex["question"])
        for i, out in enumerate(outputs):
            print(f"  [{i}] {out!r}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
