# Prototype Spec

## Two-Week Go/No-Go: Multi-Agent Retention Localization

*Draft v2, July 2026*

---

## Goal

Answer one question before any larger investment:

**When a task-needed fact is removed at a handoff, does the retention score drop in the right place?**

Nothing here is publication quality. This is a kill-check.

## Task type

Synthetic multi-hop factual QA. Fabricated facts the model cannot know from pretraining, so any correct answer must come from the handoff messages, not model memory.

Example:
- Evidence: The author of *The Glass Orchard* is Mira Talen. Mira Talen's first novel was *North Bridge*. *North Bridge* was released in 1987.
- Question: What year was the first novel by the author of *The Glass Orchard* released?
- Answer: 1987

## Agent roles

Three agents in a chain:
1. **Retriever** — selects the facts relevant to the question from the evidence.
2. **Reasoner** — chains the facts toward the answer.
3. **Answerer** — produces the final answer.

## Message format

Structured JSON, so specific pieces can be deleted, corrupted, or compressed cleanly:

\`\`\`json
{
  "known_facts": [],
  "reasoning_summary": "",
  "answer_candidate": ""
}
\`\`\`

## Model stack

- **Agents:** hosted API model, for speed.
- **Reader:** separate frozen open-weight model (Qwen / Llama / Mistral class). Held fixed across all runs.
- **Scoring:** binary exact recovery first (see below); logprob/LLM judge later.

## Recoverability score

**v0 (binary exact recovery).** For each message, prompt the frozen reader:

\`\`\`
Given only the message below, answer the question.
If the answer is not recoverable, output UNKNOWN.

Score:
1 = exact answer recovered
0 = not recovered
\`\`\`

Track retention across the chain as a curve of these scores. Do not overcomplicate the estimator yet.

**Later upgrade.** R_i = P_reader(gold answer | message, question) using logprobs or multiple-choice scoring.

**Corruption needs two scores, not one.** Because recoverability is defined against a target answer, a corrupted message has low recoverability of the *correct* answer but high recoverability of the *wrong* one. So track both:

\`\`\`
R_correct = recoverability of gold answer from message
R_corrupt = recoverability of corrupted answer from message
\`\`\`

## Fault injection schema

| Fault type | What happens | Expected signal |
| --- | --- | --- |
| Benign compression | Removes irrelevant facts | R_correct stays stable |
| Destructive deletion | Removes answer-needed fact | R_correct drops, R_corrupt does not rise |
| Corruption | Replaces needed fact with wrong fact | R_correct drops and R_corrupt rises |
| Re-derivation case | Fact deleted, later recovered downstream | Drop-then-recovery pattern |

Separating deletion from corruption is part of the core claim, not an afterthought. The method must not merely detect "loss."

## Two-stage prototype

**v0a — Detection test.** Inject faults only at Agent 2. Question: does retention drop when needed information is removed? (Detection only.)

**v0b — Localization test.** Inject faults at Agent 1, Agent 2, and Agent 3. Question: does the largest drop point to the correct handoff? This is the real localization test, because the fault location now varies. The baselines only become meaningful here.

## Baselines to beat (in v0b)

- Random
- Blame-last-agent
- Blame-longest-message
- Blame-shortest-message

## Pass / fail criteria

The prototype passes only if all hold:
1. Retention-drop method beats random.
2. Beats blame-last.
3. Beats shortest-message and longest-message heuristics.
4. Benign compression is not falsely flagged most of the time.
5. Drop-then-recovery is detected as a pattern, not treated as a plain failure.

Beating chance alone is not a pass. If retention and correctness diverge with no detectable pattern, we stop.

## Dataset

Minimum 20 synthetic examples; 50 if easy to generate.

Conditions:
- Clean
- Benign compression
- Destructive deletion
- Corruption
- Re-derivation (added after first run)

Each row:

\`\`\`json
{
  "id": "ex_001",
  "evidence": [],
  "question": "",
  "answer": "",
  "corrupted_answer": "",
  "needed_facts": [],
  "irrelevant_facts": [],
  "fault_type": "",
  "fault_agent": 2
}
\`\`\`

## Main outputs per run

- Retention curve per example
- Largest-drop handoff
- Predicted fault location
- False-positive rate on benign compression
- Drop-then-recovery cases detected

## Logging

Every run recorded in \`experiment_log.md\`:

\`\`\`md
## Run 001
Date:
Model stack:
Dataset size:
Fault types:
What worked:
What failed:
Next change:
\`\`\`
