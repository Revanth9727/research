"""
baselines.py — dumb fault-location predictors for v0b comparison.

Four baselines that predict fault location without using retention scores.
Built now; exercised in v0b where fault location varies across agents 1/2/3.
In v0a (all faults at Agent 2), these establish the comparison point.

Usage:
    from baselines import run_all_baselines
    predictions = run_all_baselines(messages)
"""

from __future__ import annotations

import random

HANDOFFS = ["agent1_to_agent2", "agent2_to_agent3", "agent3_final_output"]


def _message_length(m: dict) -> int:
    """Total character count across all fields of a message."""
    return (
        sum(len(f) for f in m.get("known_facts", []))
        + len(m.get("reasoning_summary", ""))
        + len(m.get("answer_candidate", ""))
    )


def blame_last(messages: dict) -> str:
    """Always predict the last inter-agent handoff (agent2_to_agent3)."""
    return "agent2_to_agent3"


def blame_random(messages: dict, seed: int | None = None) -> str:
    """Uniform random prediction over the three handoffs."""
    rng = random.Random(seed)
    return rng.choice(HANDOFFS)


def blame_longest_message(messages: dict) -> str:
    """Predict the handoff whose output message is longest."""
    handoff_to_msg = {
        "agent1_to_agent2":    messages.get("m1"),
        "agent2_to_agent3":    messages.get("m2_faulted") or messages.get("m2_clean"),
        "agent3_final_output": messages.get("m3"),
    }
    valid = {h: m for h, m in handoff_to_msg.items() if m is not None}
    if not valid:
        return "agent2_to_agent3"
    return max(valid, key=lambda h: _message_length(valid[h]))


def blame_shortest_message(messages: dict) -> str:
    """Predict the handoff whose output message is shortest."""
    handoff_to_msg = {
        "agent1_to_agent2":    messages.get("m1"),
        "agent2_to_agent3":    messages.get("m2_faulted") or messages.get("m2_clean"),
        "agent3_final_output": messages.get("m3"),
    }
    valid = {h: m for h, m in handoff_to_msg.items() if m is not None}
    if not valid:
        return "agent2_to_agent3"
    return min(valid, key=lambda h: _message_length(valid[h]))


def run_all_baselines(messages: dict, seed: int | None = None) -> dict[str, str]:
    """
    Run all four baselines and return their predictions.

    messages: dict with keys m1, m2_clean, m2_faulted, m3 (any subset).
    Returns dict mapping baseline name -> predicted handoff label.
    """
    return {
        "blame_last":             blame_last(messages),
        "blame_random":           blame_random(messages, seed=seed),
        "blame_longest_message":  blame_longest_message(messages),
        "blame_shortest_message": blame_shortest_message(messages),
    }
