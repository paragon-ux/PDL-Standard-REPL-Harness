# ADR-0008: Context, session, and normative storage architecture

- Status: Accepted
- Date: 2026-09-17
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0002](0002-controller-owned-artifact-controls.md), [ADR-0003](0003-phase-projected-single-model-contexts.md), [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), [ADR-0007](0007-operationalize-negative-constraints-by-omission.md)
- Related requirements: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md)

## Context

The controller-gated pseudocode confirmation protocol requires strict isolation across compilation stages, evaluation runs, and interactive sessions. Two operational challenges emerged as the protocol scaled to multi-turn developer interactions and extensive test batteries:

1. **Scaffolding Duplication and Storage Bloat:** Earlier implementations provisioned execution workspaces by copying complete static templates containing over 35 boilerplate files and directories per invocation. Across multi-hundred trial qualification batteries, this produced tens of thousands of redundant disk artifacts, consuming excessive file handles and causing significant file-system traversal latency (particularly on Windows NTFS).
2. **Context Flatlining in Multi-Turn Sessions:** In continuous interactive sessions, successive developer tasks require distinct lifecycle boundaries. Without a formal hierarchical separation between overarching session state and substantive task execution, rejected candidate drafts, intermediate procedural explorations, and conversational chatter from prior tasks threatened to leak across task boundaries or complicate clean audit records.
3. **Normative Standards Invariance Across Environments:** Standard protocol definitions, execution contracts, and JSON schemas must remain strictly immutable and verifiable across diverse execution environments (local checkouts, continuous integration containers, monorepo subtrees, and developer scratchpads) without coupling protocol definitions to any specific version control root.

## Decision drivers

- Eliminate static file-system duplication and file-handle exhaustion during workspace initialization.
- Provide a clean, two-level hierarchical lifecycle separating multi-turn session persistence from individual task epochs.
- Enforce clean task execution boundaries per [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md) across multi-turn interactions, allowing confirmed deliverables to chain into subsequent tasks while discarding transient drafting history.
- Decouple normative protocol standards and verification contracts from specific project directories while preserving byte-for-byte replay deterministic hashing.
- Ensure seamless cross-platform file-system performance across Windows NTFS and POSIX ext4 filesystems.

## Decision

The harness SHALL partition protocol resources into two decoupled architectural tiers—the **Static Normative Store ("The Brain")** and the **Dynamic Operational Workspace ("The Hands and Feet")**:

### 1. The Normative Store ("The Brain")
- Canonical protocol standards, schemas, and execution verification contracts SHALL reside in an operator-scoped, version-namespaced directory (`~/.pdlt/versions/<version>/`).
- Active target projects SHALL declare their required protocol version using an immutable version pin (`.pdlt-version` or `pdlt.json`) in the project directory tree. If no pin is declared, the resolver falls back to the configured global default version or harness bundled standards.
- Replay and execution determinism SHALL be guaranteed by content-addressed hashing of serialized string clauses rather than physical disk paths. Normative standard bundles are cryptographically verified and immutable once installed.

### 2. Zero-Template Dynamic Materialization ("The Hands and Feet")
- Pre-allocated static workspace templates are permanently retired.
- Operational run workspaces SHALL be initialized as lean, empty containers containing only basic state and event directories.
- Stage-specific execution contexts and directories (`stages/<stage_id>/input/` and `stages/<stage_id>/output/`) SHALL be materialized strictly on-demand by the controller when an operation is executed.
- Intermediate stage outputs are maintained in lightweight, dynamic operational files (`current.json`, `current.md`, `events.jsonl`).

### 3. Two-Level Invariant Session Hierarchy
Multi-turn conversational workflows SHALL be formally structured into two distinct lifecycle levels:
- **Level 1: Substantive Task Epoch (`turns/turn_###/`)**: An indivisible protocol cycle from initial user instruction, through interpretation and approach confirmation, to final deliverable completion (`CLOSED_SUCCESS` or `CLOSED_CANCELLED`). Each task epoch owns its self-contained stage directory, controller state machine, and discrete event log.
- **Level 2: Interaction Invocations (`input/####-<operation>/`)**: Conversational reviews, clarification queries, and inline corrections within a task epoch execute as sequentially numbered invocations inside that epoch's stage directory, preserving granular telemetry without fragmenting task boundaries.

### 4. Cross-Turn Deliverable Chaining
- When a task epoch completes with `CLOSED_SUCCESS`, its verified final deliverable is published to its stage execution record.
- When a user initiates a subsequent task in the same session, the session engine initializes a fresh task epoch (`turn_###+1`).
- Per [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), the new task epoch ingests the confirmed deliverable of the preceding epoch as clean, inactive background input. Intermediate draft revisions, rejected procedural plans, and conversational negotiation from prior epochs are excluded from the new task's compiled context.

## Consequences

### Positive

- **Storage Efficiency:** Static file creation per workspace drops from 35 files to zero. Total disk artifacts created per task are reduced by over 85%, eliminating file-system traversal delays and storage exhaustion during large automated runs.
- **Hermetic Task Boundaries:** Multi-turn sessions retain clean execution boundaries. Conversational noise and stale drafts cannot contaminate subsequent tasks.
- **Portability and VCS Independence:** Normative standards are shared across all local projects without duplicating copies in git repositories, supporting scratchpad projects, monorepo subtrees, and headless CI pipelines alike.
- **Deterministic Auditability:** Every substantive task possesses a completely self-contained, reproducible record of its prompts, plans, review invocations, and emitted deliverables.

### Negative

- **Directory Depth:** Structured multi-turn workspaces introduce hierarchical directory paths (`sessions/<id>/turns/turn_###/stages/...`). Component tokens must remain concise to remain comfortably within path length limits on Windows NTFS.
- **Initial Store Provisioning:** Environments running without an internet connection or bundled repository fallback require the normative store directory (`~/.pdlt/versions/<version>/`) to be pre-provisioned.

## Alternatives considered

### Anchoring normative standards strictly in project repository roots
Rejected. Mandating that every project repository store a complete local copy of standards and schemas causes extensive file duplication across projects and branches, and prevents protocol use in scratchpad directories or non-git workspaces.

### Flat, single-level session directories
Rejected. Storing all multi-turn interactions in a single flat workspace causes rejected drafts from early tasks to intermingle with later tasks, making deterministic replay difficult and increasing the risk of accidental context leakage across unrelated objectives.

### Copy-on-write filesystem templates
Rejected. Relying on OS-specific copy-on-write mechanisms (such as reflink or symlinks) introduces non-portable dependencies that fail or require elevated administrative privileges on Windows systems. Dynamic on-demand materialization provides cross-platform speed without privileged system calls.
