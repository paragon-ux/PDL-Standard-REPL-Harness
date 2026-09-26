# ADR-0009: Require decomposed Result Pseudocode with cited execution evidence

- Status: Accepted (prototype; feature-gated per TRD-0003 RS-10)
- Date: 2026-09-18
- Parent decision: [ADR-0005](0005-optional-result-pseudocode.md)
- Related requirements: [TRD-0003: Result Pseudocode Decomposition Standard](../trd/0003-result-pseudocode-decomposition-standard.md)
- Related decisions: [ADR-0003](0003-phase-projected-single-model-contexts.md), [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), [ADR-0008](0008-context-and-session-management.md)

## Context

Live build orchestration (Distributed WAL storage engine, model z-ai/glm-4.7,
sessions `runs/wal-build`, `runs/wal-exp2b`, `runs/wal-exp4`, 2026-09-17/18)
demonstrated a structural continuity failure across task epochs:

1. Phase projections launder source material out of the execution phase
   (ADR-0003 inclusion lists). `REQUIRED_TASK_INPUTS` and
   `SUPPLIED_EXECUTION_INPUT_SOURCE` were `null` in every observed EXECUTE
   call; the executor conditioned only on confirmed pseudocode summaries.
2. Consequence: revision epochs hallucinated parallel architectures
   (`WALIndex(idx_path)`, `perform_recovery(wal_dir)`, invented record
   formats) against preserved modules the executor had never seen.
3. Controller-side byte-exact chaining of the prior confirmed deliverable
   into `REQUIRED_TASK_INPUTS` eliminated API hallucination (diffs collapsed
   from ~100% rewrites to 0–7 changed lines) but did not steer the work: with
   full code visibility the executor still re-architected an unconstrained
   component and fabricated test expectations (`expected_max = 3`) to force a
   pass.
4. Pseudocode summaries are the only representation with enough semantic
   density (intent + approach) to survive projection boundaries, but a
   self-contained summary re-states results from memory — the hallucination
   surface itself.

## Decision

The EXECUTE operation SHALL emit, alongside the native deliverable, a
**decomposed Result Pseudocode** (Result IR) that is:

- **co-referential** with the confirmed Prompt Pseudocode: requirement IDs are
  derived mechanically from the confirmed prompt body and every ID SHALL be
  reconciled exactly once with status `satisfied | partial | open`;
- **evidence-cited**: every component, status, and open defect SHALL cite a
  workspace-resolvable artifact path; every factual claim SHALL carry a
  verbatim `observed` quote; invented paths, sections, quotes, and IDs are
  mechanical validation failures;
- **mechanically validated** by the controller (host-side, stdlib): schema
  shape, coverage/uniqueness, path resolution, verbatim section/observation
  checks; exactly one operator-correction retry on failure; persistent
  failure published and scored, never masked;
- **chained forward**: continuation epochs receive the prior validated Result
  IR beside the byte-exact prior deliverable; reconciliation state is
  authoritative across process restarts (restore included).

Structured output is mandatory for citations: the IR is a schema-shaped JSON
object whose evidence fields the controller validates against the filesystem.
Free-text result narration alone is not a conforming result artifact under
this decision.

## Consequences

### Positive

- Cross-turn continuity no longer depends on unmanaged summaries: intent
  (dense IR) and existence (resolvable citations) travel together.
- Hallucinated expectations and fabricated evidence become mechanically
  invalid rather than merely implausible.
- Revision epochs are steered by reconciliation state ("close D1") instead of
  underspecified defect reports.
- Validation is controller-owned and model-agnostic; containment invariants
  are preserved (feature-gated; recorded paths byte-identical).

### Negative

- Generation cost per epoch increases (decomposition + citations).
- Requirement-ID derivation is mechanical and therefore approximate until the
  prompt IR gains first-class requirement IDs (future contract revision).
- Evidence citations multiply context size on large projects; resolution is
  controller-side and cheap, but the injected union (IR + bytes) requires a
  size policy.

## Alternatives considered

### Byte-exact chaining only (implemented first)

Shipped as the interim mechanism (`REQUIRED_TASK_INPUTS` chaining, restore
re-population). Retained as the substrate under the IR: it removes API
hallucination but not goal drift. Superseded as the sole mechanism.

### Free-text Result Pseudocode (ADR-0005 unmodified)

Rejected: prose decompositions are unauditable; the WAL sessions produced
five hallucinated fix cycles under free-text steering.

### Controller-side cumulative project merge

Deferred: merging partial deliverables into a canonical project state is
sound but heuristics-laden; the delivery policy "deliverables are full
project states" plus per-epoch IR chaining achieves continuity without a
merge heuristic.
