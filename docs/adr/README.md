# Architecture decision records

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](0001-controller-gated-pseudocode-protocol.md) | Accepted | Adopt the umbrella controller-gated pseudocode protocol. |
| [ADR-0002](0002-controller-owned-artifact-controls.md) | Accepted | Put artifact UI and deterministic branching in the host controller. |
| [ADR-0003](0003-phase-projected-single-model-contexts.md) | Accepted | Use controller-compiled phase contexts with one model as the core implementation. |
| [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md) | Accepted | Execute from a clean projection containing the confirmed pair and required task inputs. |
| [ADR-0005](0005-optional-result-pseudocode.md) | Accepted | Offer Result Pseudocode as an optional execution-output mode. |
| [ADR-0006](0006-bounded-pre-execution-reasoning.md) | Accepted | Limit pre-execution reasoning and avoid materially consequential guessing. |
| [ADR-0007](0007-operationalize-negative-constraints-by-omission.md) | Accepted | Operationalize negative constraints by omission. |
| [ADR-0008](0008-context-and-session-management.md) | Accepted | Separate normative store from dynamic zero-template session workspaces. |
| [ADR-0009](0009-result-pseudocode-decomposition-standard.md) | Accepted (prototype, feature-gated) | Require decomposed Result Pseudocode with mechanically validated evidence citations, chained across epochs. |
| [ADR-0010](0010-pydantic-wire-enforcement.md) | Accepted | Pydantic v2 schema enforcement and automated operator retry corrections for wire contracts. |
| [ADR-0011](0011-in-memory-vfs-and-microvm-sandboxing.md) | Accepted | Software-defined in-memory VFS context flow and ephemeral MicroVM agent sandboxing via MCP. |
| [ADR-0012](0012-system-1-decision-models-via-rlcd.md) | Accepted | Realign Track L to System 1 decision models (Laya/Jev) aligned via RLCD contrastive distillation. |
| [ADR-0013](0013-substantive-correctness-verification.md) | Accepted | Verified execution and bidirectional witness retention for substantive correctness. |
| [ADR-0014](0014-dual-plane-boundary-and-wire-conformance.md) | Accepted | Dual-plane boundary architecture: positive structural guidance, wire-level Pydantic contract enforcement, and tripartite clause governance. |
| [ADR-0015](0015-model-synthesized-verification-and-confinement-boundaries.md) | Accepted | Model-synthesized verification and confinement boundaries in ephemeral sandboxes. |
| [ADR-0016](0016-pydantic-ssot-wire-and-deliverable-boundary-enforcement.md) | Accepted | Pydantic Single Source of Truth (SSOT) for wire and deliverable boundary enforcement. |
| [ADR-0017](0017-dual-plane-runtime-realignment-and-mrv-solver-governance.md) | Accepted | Dual-Plane Runtime Realignment: System 1 (Jev) Baseline & Constraint-Ordered Solver Governance. |
| [ADR-0018](0018-elimination-of-regex-heuristics-in-verification-and-reconciliation-integrity.md) | Accepted | Elimination of Regex Heuristics in Substantive Verification & Reconciliation Semantic Integrity. |
| [ADR-0019](0019-headless-waiting-input-exit-and-wire-tolerance.md) | Accepted | Headless WAITING_INPUT Exit Code & Execution Wire Input Tolerance. |
| [ADR-0020](0020-system-1-environment-conditioned-refusal-routing.md) | Accepted | System 1 Environment-Conditioned Boundary Interception & Immediate Refusal Routing. |

The records are intentionally separated so UI, context construction, execution
isolation, output representation, and reasoning policy can evolve without
replacing the entire protocol decision.

