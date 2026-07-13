# Project Prospectus

## Measuring Information Survival in Multi-Agent LLM Pipelines

*Draft for discussion, July 2026*

---

## 1. Problem

Multi-agent LLM systems now handle complex tasks by chaining several agents together, each passing work to the next. They fail often, and when the final answer is wrong, we usually cannot tell which agent caused it. In practice this means rerunning the whole pipeline instead of fixing the one broken step, which is slow and expensive.

Failure attribution is an established research problem with a public benchmark (Who&When, ICML 2025) and a fast-growing set of methods: LLM-judge approaches, spectrum analysis over replayed trajectories (Famas), RL-trained tracer models (AgenTracer-8B), and dependency-graph tracing (GraphTracer). Every one of these is behavioral or structural: it judges transcripts, replays trajectories, or traces which agent depended on which.

None of them answers a more basic question. When an agent's output gets shorter or changes, did it correctly trim irrelevant detail, or did it destroy the information the answer depended on? Both look the same on the surface. Only one is a fault.

## 2. Central claim

Failures in agent pipelines are not all the same kind. At minimum they separate into:

- **Benign compression** — only irrelevant detail is dropped. Not a fault, and should not be flagged as one.
- **Destructive deletion** — answer-relevant information becomes unrecoverable.
- **Corruption** — information is replaced with something wrong.

Guiding hypothesis: fault localization improves when we treat these as fundamentally different failure modes, and we operationalize that hypothesis with an information-retention estimator. The taxonomy and the method are one argument. The concept predicts that measuring retention should localize destructive faults specifically; the estimator tests whether that prediction holds.

## 3. Approach

Instead of judging which agent *appears* responsible, we measure whether the information the task needs actually *survives* each handoff. Each inter-agent message is treated as an information bottleneck, and we quantify how much task-relevant information passes through it. A sharp drop flags a candidate failure point.

**Definition.** For message $m_i$ at agent $i$ and correct answer $A$, recoverability is $R_i = f(m_i, A)$: how well $A$ can be recovered from $m_i$ under a fixed reader. A sharp drop in $R_i$ across a handoff flags candidate destructive loss.

**Measurement.** We freeze a reader model and measure $R_i$ at each message. We instantiate the framework with V-information (usable information) because it measures the information a downstream decision-maker can actually act on, which is exactly what the next agent consumes. The framework admits alternative notions of recoverable information.

## 4. The hardest question

Agents do not just carry information, they compute. Agent 2 can delete a fact and Agent 3 can re-derive it, in which case the pipeline is fine even though information was locally lost. So "information survived" and "the pipeline worked" are not identical. They diverge exactly when a downstream agent recomputes.

This is the deepest question in the project, not a flaw: when is information transmission sufficient to explain multi-agent reasoning? If re-derivation turns out to be common, we learn something fundamental about how these systems work. If it is rare, that is equally informative. We measure where task-relevant information stops being *locally recoverable*, and we treat the drop-then-recovery event as a detectable finding rather than an error. The prototype (Section 8) is built to answer this before any large investment.

## 5. Assumptions

The approach rests on three assumptions, which the prototype is designed to test rather than take for granted:

1. Task-relevant information is represented in the intermediate messages.
2. Downstream agents primarily consume those messages rather than regenerate missing information.
3. Recoverability under a strong reader approximates recoverability for the downstream agent.

Assumption 2 is the one most at risk, and it is the focus of the make-or-break prototype test.

## 6. Handling the main objections

**"Recoverable by whom?"** Recoverability depends on reader strength, so we do not pick one reader. We test a ladder of readers, weak to strong. A drop that persists even for the strongest reader signals real loss; a drop a stronger reader recovers signals reader weakness, and the curve shows it. We claim only "recoverable under this reader family," never objectively recoverable, since no finite ladder reaches every possible reader.

**Defining responsibility.** "We injected the fault, so we know the culprit" is not automatically true, because a downstream agent that could have recovered a deleted fact also shares blame. We adopt the field's existing definition: the culprit is the earliest agent whose correction fixes the outcome (as in Who&When and GraphTracer), so we are not inventing a contested standard.

**Out of scope.** Aggressive-but-recoverable compression can preserve the answer while forcing far more downstream reasoning, making the pipeline more fragile without deletion or corruption. We flag this "reduced robustness" category as future work rather than model it here.

## 7. Two-paper plan

**Paper 1 — the benchmark.** Built first. It is the safer, higher-citation contribution and may prove the more influential of the two. It provides agent traces with typed faults and ground truth by construction: information deletion, corruption, benign abstraction (a negative control no existing benchmark has), hallucinated reasoning, and correct-evidence-but-wrong-inference. Injected faults are verified by counterfactual replay so the injected fault is genuinely the decisive one. Injected faults are mixed with naturally occurring failures harvested from real agent runs, so the benchmark cannot be dismissed as built to favor our own method. It is useful to the field independent of our localization method.

**Paper 2 — the method.** Built and tested on Paper 1's data. It presents the retention estimator and the compression / deletion / corruption distinctions, and shows the method localizes destructive faults while correctly ignoring benign compression, where judge and tracer methods cannot tell them apart. It is compared head-to-head on the public Who&When benchmark against LLM-judge, AgenTracer, and GraphTracer baselines. A repair experiment (locate the culprit, rerun only that agent, measure how often the task is fixed) turns localization into an end-to-end result. Primary domain is question answering, with at least one coding or retrieval pipeline as a generalization check.

## 8. Go/no-go prototype (first two weeks)

Build a toy 3-agent chain and run two tests:

1. **Localization test.** Inject a typed fault. Confirm the largest retention drop localizes the culprit better than all of: blame-last, blame-longest-message, blame-shortest-message, and random. Beating chance alone is not a pass, because dumb heuristics beat chance.
2. **Make-or-break test.** Inject a deletion at Agent 2, let Agent 3 re-derive it, and check whether the method blindly reports failure or detects the drop-then-recovery. This decides whether the framing survives.

If both hold, commit. If retention and correctness routinely diverge with no detectable pattern, the idea is in trouble, and we will know in two weeks instead of a year.

## 9. Resources and constraints

All datasets are open and public. Who&When is public, the benchmark we build is released openly, and open-weight models (Qwen, Llama, Mistral class) serve as the frozen readers for reproducibility. Models used to generate traces are unrestricted. Compute needs are dominated by repeated cheap inference for the reader-based estimator, not large-scale training; modest GPU access on Azure is sufficient. A small trained retention probe or attribution baseline is an optional extension if compute allows.

## 10. One-line pitch

Everyone races to guess which agent broke. We measure whether the information the task needs actually survived, and separate agents that compressed from agents that destroyed.
