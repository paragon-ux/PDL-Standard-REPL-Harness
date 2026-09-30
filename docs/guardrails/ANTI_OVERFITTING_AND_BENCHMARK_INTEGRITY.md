# Anti-Overfitting and Benchmark Integrity Guardrail (GUARD-01)

## Executive Summary & Normative Status

This document defines the **Normative Guardrail Standard** for the PDL-Taskmaster harness (`pdl-taskmaster`). It establishes immutable architectural invariants to prevent **benchmark gaming, Goodhart drift, prescriptive prompt injection, and artificial heuristic overfitting**.

The core thesis of the PDL protocol is:
> **The protocol exists to enforce faithful reasoning, falsifiable procedural commitments, and tamper-evident verification against the USER'S PROMPT—never to substitute the harness's own synthetic heuristics for genuine model reasoning.**

When the harness injects synthetic algorithmic strategies, forces script execution for non-computational tasks, or hardcodes token patterns targeting specific benchmark probes, it violates Goodhart's Law, compromises publication integrity, and actively degrades the model's reasoning on legitimate user tasks.

---

## 1. Anatomy of the Failure: How Goodhart Drift Corrupted Reasoning

During the development and optimization of the 105-prompt catalogue benchmark, prescriptive shortcuts were incrementally introduced into runtime source files to guarantee green scoreboard passes:

1. **Forced Algorithmic Injection (`session_engine.py`)**:
   When `carried_raw` was empty, the engine injected:
   `carried = ["EXECUTE a Python backtracking solver script to search for the partition triples."]`
   The harness ceased to be an objective referee and became an active, prescriptive co-author.

2. **Keyword Over-Matching (`problem_class.py`)**:
   General vocabulary (`sisters?`, `brothers?`, `family relationship`, `logic puzzle`, `riddle`) was added to `_COMBINATORIAL_PATTERNS`. This deterministically forced general analytical reasoning queries into the verified combinatorial execution pipeline.

3. **Compulsory Script Generation (`api_worker.py`)**:
   Normative guidelines instructed the worker: `"Always emit a RESULT containing the complete Python solver script and Result IR"`.

4. **Benchmark-Targeted Refusal Regexes (`activation_route.py`)**:
   Specific prompt entities (`frostbitedb`, `2026-2029 nobel prize`) were hardcoded directly into deterministic regexes to bypass model evaluation and trigger immediate refusals.

### The Real-World Failure Mode: The Alice Siblings Pathology
In session `session-20260929-234002`, the user posed a classic symbolic deduction riddle:
> *"Alice has N brothers and she also has M sisters. How many sisters does Alice's brother have?"*

Because of the architectural crutches described above:
- The query matched `sisters?` in `_COMBINATORIAL_PATTERNS`.
- The engine injected: `"EXECUTE a Python backtracking solver script to search for the partition triples."`
- The model was forced to draft a plan containing `"CONSTRUCT a Python backtracking solver script"`.
- Because Python scripts cannot execute unbound variables ($N, M$) without value assignment, the model had to **fabricate synthetic concrete values** (`N = 3, M = 4`).
- Cornered into writing executable script code and generating a sandbox `WITNESS` dictionary, the model's logical deduction derailed into writing:
  ```python
  # All siblings share the same sisters, so any brother has M sisters.
  solution = M
  ```
- **The model emitted $M$ instead of the correct answer $M + 1$** (Alice herself is female and is one of the brother's sisters).

The harness's benchmark crutches converted a trivial symbolic logic problem into a failed numerical simulation with fabricated inputs.

---

## 2. Inviolable Guardrail Invariants

The following five invariants are binding across all code, PRs, ADRs, and runtime modifications:

### GUARD-01: Zero Prescriptive Approach Injection
1. If the workspace `approach_sources` list is empty, `carried` MUST remain strictly empty (`carried = []`).
2. The harness MUST NEVER synthesize, default-assign, or inject algorithmic methods, search strategies, solver types, or data structures (e.g. `"backtracking"`, `"Algorithm X"`, `"DLX"`, `"dynamic programming"`, `"MRV"`, `"partition triples"`) into `CARRIED_APPROACH_SOURCES`.
3. The choice of solution strategy belongs entirely to the worker model based on the user's substantive prompt.

### GUARD-02: Prohibition of Benchmark Token Targeting
1. No regular expression, keyword lookup, or deterministic classifier in `src/pdl_taskmaster/` may target specific benchmark prompt text, fictional test entities, or dataset artifacts (e.g. `frostbitedb`, `nobel prize`, `schur triples`, `family relationship`).
2. Refusal classifiers (`INTERPRET_ACTIVATION`, System 1 recipes) must operate on general environmental conditions (`sandbox_network == False`, `policy_scope == "technical"`, `knowledge_cutoff`) or evaluate semantic intent via model scoring.
3. Test fixtures testing boundary refusals must supply their parameters via environment variables or mock configs, never via hardcoded runtime production tokens.

### GUARD-03: First-Class Symbolic & Analytical Reasoning
1. The harness MUST NOT assume every problem is a code execution problem. Analytical proofs, symbolic mathematics, word problems, and logical deductions are first-class deliverables.
2. For problems with symbolic parameters ($N, M, x, \dots$), the harness MUST NOT compel the model to fabricate numerical values or produce executable Python scripts unless the user explicitly requested numerical simulation or code implementation.
3. Plan soundness validators (`plan_soundness.py`) MUST accept pure procedural deduction and analytical derivation plans without demanding code execution keywords (`python`, `script`, `backtracking`).
4. Result IR schemas MUST fully support non-code deliverables (`files: []`, `path: "execution://body"`) with substantive reconciliation grounded in direct textual deduction.

### GUARD-04: Separation of Protocol Governance from Task Performance
1. The harness is a **protocol governor**, not an AI task solver. Its authority is strictly limited to:
   - Enforcing stage transitions (`PROMPT_REVIEW` $\to$ `PLAN_REVIEW` $\to$ `CLOSED_SUCCESS` / `CLOSED_CANCELLED`).
   - Validating artifact schemas (PDL formatting, Result IR shape).
   - Validating witness cryptographic integrity when witness verification is requested.
2. The harness MUST NEVER attempt to "help" the model solve the problem by steering its approach or pre-selecting answers in prompt instructions.

### GUARD-05: Automated Static & Dynamic Anti-Gaming Verification
1. All anti-overfitting invariants must be validated by automated unit tests and static linters in `tests/test_harness_anti_overfitting.py`.
2. Any introduction of hardcoded domain strings into prompt builders, or benchmark entity names into production regexes, MUST fail `pytest` and block `pdlt verify`.
