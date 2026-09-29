# ADR-0015: Model-Synthesized Verification and Confinement Boundaries in Ephemeral Sandboxes

- **Status:** PROPOSED
- **Date:** 2026-09-27
- **Related:** [ADR-0011 In-memory VFS & microVM sandboxing](0011-in-memory-vfs-and-microvm-sandboxing.md), [ADR-0013 Substantive correctness verification](0013-substantive-correctness-verification.md), [ADR-0014 Dual-plane boundary architecture](0014-dual-plane-boundary-and-wire-conformance.md)
- **Evidence:** `session9-v-2-4-0.txt` (witness retention gap), `session10-v-2-4-0.txt` (external repo `FileNotFoundError` on `RESULT_STANDARD.md` disk read), and review analysis of runaway verifier accumulation.

---

## Context

ADR-0013 established verified execution, bidirectional witness retention, and OS-native process sandboxing to address ungrounded confabulation. However, expanding this pattern surfaced two architectural risks:

1. **The Runaway Verifier Bottleneck (Loss of Model Independence):**
   If the harness is required to implement bespoke Python verifiers for every problem class (`partition_sum_triples.py`, `graph_coloring.py`, `subset_sum.py`, `clique.py`, etc.), the harness degrades from an extensible agentic orchestrator into a brittle, hand-maintained test suite. 
   While generative LLMs struggle with combinatorial search in pure autoregressive token emission (confabulating proofs and claiming false negatives), LLMs are exceptionally reliable at writing concise $O(N)$ or $O(N^2)$ verification checkers for candidate solutions. 

2. **File-Pointer Fragility and Prompt Tampering:**
   As demonstrated in `session10-v-2-4-0.txt`, reading normative prompt specifications dynamically from filesystem paths (`contracts/standards/RESULT_STANDARD.md` relative to `--candidate-repo`) crashes with `FileNotFoundError` whenever the REPL runs outside the harness source root (e.g. in `PDLt-Test` or consumer repositories). Furthermore, dynamic disk reads for protocol-level prompt injection instructions introduce prompt tampering and injection vulnerabilities if the workspace files are modified.

---

## Decision

### 1. Clear Division of Responsibilities

The system formalizes the boundary between harness governance and model problem-solving:

* **The Harness Provides Confinement and Invariant Enforcement:**
  - **Deterministic OS-Native Sandbox (`ExecutionSandbox`):** Enforces hard kernel-level limits (Windows Job Objects via `ctypes` calling `kernel32.dll`, POSIX `setrlimit`), 256MB RAM ceilings, 5.0s timeouts, zero outbound socket access, and ephemeral scratchpad isolation.
  - **Wire Contract Enforcement (`ResultIRData.witness`):** Validates the structural schema of emitted witnesses (`PositiveWitness` vs. `NegativeWitness`).
  - **Immutable Canonical Instructions:** Standard normative prompt clauses (such as `RESULT_STANDARD` instructions) are compiled in-code as immutable constants, eliminating disk-pointer fragility and workspace file-tampering risks.
  - **Grounded Introspection Retention:** Retains and projects verified witnesses into cross-turn context, explicitly forbidding confabulation when no witness was retained.

* **The Model (sys2) Synthesizes Solution and Self-Verification:**
  - The model writes its search/solver script AND its own verification checker.
  - Both run inside the ephemeral `ExecutionSandbox` during the `50_execution` stage.
  - The model packages the verified solution or negative search certificate into `result_ir.witness`.

### 2. Harness-Resident Verifiers as Calibration Oracles Only

Harness-resident checkers (such as `PartitionSumTriplesChecker`) SHALL be maintained strictly as **gold-standard calibration fixtures** (ground-truth regression oracles for `session9` and qualification benchmarks). 

The harness SHALL NOT accumulate an unbounded library of handcrafted domain solvers. For uncalibrated problem domains requiring verified execution, the harness uses `FallbackChecker`, which validates structural schema conformance, certificate completeness (`search_exhausted == True`), and marks output as `provisional` without preempting the model's sandboxed self-verification.

### 3. Live REPL Zero-Regression Pre-Confirmation Invariant

To ensure that offline test fixtures and unit mocks (`pytest`) do not conceal live wire payload formatting defects, dynamic path resolution bugs, or model schema enforcement errors, the release of any protocol or host modification SHALL be governed by a strict Live REPL Verification Invariant:

* **Live REPL Operational Stage Traversal Mandate:** Every completed pass or bugfix MUST execute a live verification run using the terminal REPL in the designated test workspace (`C:\Users\USER\Desktop\Frameworks\PDLt-Test`) with Dev Mode (`--dev`) enabled.
* **Full Protocol Traversal:** The live verification pass MUST execute across all active operational stages (`PROMPT_REVIEW` → `PLAN_REVIEW` → `CLOSED_SUCCESS`) with zero unhandled exceptions, zero unhandled `WireError` regressions, and clean stage transitions.
* **Structured Failure Logging:** Any major failure or contract violation encountered during development or live REPL runs MUST be recorded in the mechanized ledger `docs/governance/regressions-log.jsonl` detailing cause types, problem statements, type effects, and type solutions before confirming the fix.

---

## Consequences

- **Model Independence Preserved:** The harness remains an agentic substrate rather than an exhaustive oracle library; the model retains autonomy to formulate solving and checking algorithms across open-ended domains.
- **Robustness Across Workspaces:** The REPL and host operate cleanly in any target workspace (including bare test directories like `PDLt-Test`) without requiring harness contract files to be copied or linked on disk.
- **Deterministic Security:** Untrusted model-generated scripts execute exclusively inside the kernel-enforced `ExecutionSandbox`, preventing denial of service, resource leaks, or network exfiltration.
- **Benchmark Stability:** The existing `session9` 45-integer Schur triples case remains permanently sealed against regression via the gold-standard calibration fixture.
