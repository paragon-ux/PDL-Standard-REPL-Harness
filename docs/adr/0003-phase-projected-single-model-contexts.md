# ADR-0003: Use phase-projected single-model contexts

- Status: Accepted
- Date: 2026-08-06
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related requirements: [TRD-0001 Sections 6 and 9](../trd/0001-controller-gated-pseudocode-protocol.md#6-canonical-state-requirements)

## Context

Interpreter, planner, and executor subagents are one possible implementation of
the protocol. They can isolate work, but they also introduce orchestration
prompts, handoff summaries, duplicated instructions, and possible translation
loss between agents or models.

The protocol is sequential and its branches are deterministic. It therefore
does not require agentic orchestration. One model can perform every phase if
the host controls state and supplies only the context required by the current
phase.

Using the same model name does not preserve hidden cognitive state between
calls. Model continuity is created by supplied context. Keeping the complete
conversation provides continuity but also retains rejected drafts and protocol
noise. Supplying only an artifact handoff is compact but can be lossy when the
handoff omits required source material.

## Decision

The core implementation SHALL use a controller-owned canonical state and a
separate controller-compiled context for each phase. It MAY use the same model
and reasoning configuration for Prompt generation, Plan generation, and
execution.

Each model call SHALL be treated as stateless. The controller, not model
identity or conversational memory, SHALL provide continuity.

The controller SHALL retain canonical source inputs outside transient model
contexts and construct phase projections using positive inclusion lists:

- Prompt phase: current authoritative request, required source references,
  Prompt Pseudocode instructions, and necessary PDL conventions.
- Plan phase: confirmed Prompt Pseudocode, planning instructions, and necessary
  PDL conventions.
- Execution phase: confirmed Prompt Pseudocode, confirmed Response Plan
  Pseudocode, required task inputs, selected output mode, tools, and applicable
  higher-priority constraints.

The controller SHALL NOT create a phase projection by forwarding the complete
conversation and asking the model to ignore irrelevant turns.

Phase-specific instruction packs MAY be derived from the existing skill, but
the complete monolithic skill SHALL NOT be required in every phase context.

Subagents, smaller phase models, and specialized model routing are deferred
optimizations. If introduced, they SHALL preserve the same controller state,
artifact contracts, and phase projections.

## Consequences

### Positive

- The initial architecture remains simpler than a multi-agent system.
- The model receives less irrelevant protocol and correction history.
- Same-model use avoids unnecessary cross-model dialect and capability
  differences.
- Source context can remain complete in controller storage without occupying
  every model call.
- Phase prompts can be measured, cached, evaluated, and optimized separately.
- Future routing changes do not alter the user-visible protocol.

### Negative

- The controller must correctly determine the minimum sufficient phase context.
- An incomplete Execution projection can silently remove a confirmed
  requirement or necessary source.
- The same model may not be the most cost-effective model for every phase.
- Multiple stateless calls do not retain unexpressed intermediate cognition.

## Alternatives considered

### Mandatory interpreter, planner, and executor agents

Deferred. This is a valid future optimization but adds machinery that is not
needed for deterministic sequential phases.

### One continuous conversation for every phase

Rejected as the target. It maximizes continuity at the cost of context growth,
rejected-draft retention, and instruction competition.

### Artifact-only handoff with no canonical source store

Rejected. The confirmed artifacts are authoritative instructions, but some
tasks still require files, evidence, datasets, or other source inputs during
execution.

