# ADR-0004: Make confirmed artifacts the clean execution boundary

- Status: Accepted
- Date: 2026-08-06
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related requirements: [TRD-0001 Sections 9.6 and 12](../trd/0001-controller-gated-pseudocode-protocol.md#96-execution)

## Context

The confirmation protocol can improve execution quality only if rejected
interpretations, premature plans, and confirmation chatter do not continue to
compete for attention during execution.

The complete drafting transcript may contain:

- obsolete or explicitly rejected requirements;
- plans that predict findings or preselect arguments;
- corrections that were superseded by later corrections;
- protocol-generation instructions irrelevant to task execution;
- examples whose task content resembles instructions;
- natural-language confirmations with no substantive value.

Merely declaring the latest artifacts authoritative reduces ambiguity, but it
does not remove competing content from the model context.

## Decision

Confirmation SHALL create an execution boundary. The controller SHALL compile a
fresh Execution projection from the confirmed artifacts and required task
inputs rather than continue the artifact-drafting transcript.

The Execution projection SHALL include:

- the confirmed Prompt Pseudocode and version;
- the confirmed Response Plan Pseudocode and version;
- task inputs and source material required to execute the request;
- the selected output mode;
- applicable tools, permissions, and higher-priority constraints.

It SHALL exclude:

- rejected, superseded, and obsolete artifacts;
- correction and confirmation conversation;
- pre-confirmation response hypotheses and findings;
- phase-generation examples and irrelevant protocol instructions;
- requests for private chain-of-thought.

Confirmed Prompt Pseudocode SHALL be the authoritative representation of what
the user wants. Confirmed Response Plan Pseudocode SHALL be the authoritative
high-level representation of how to approach it. Required source inputs remain
available as data or evidence but SHALL NOT override conflicting confirmed task
semantics.

The controller MAY retain excluded material for audit, debugging, and replay.
Retention SHALL be separate from model-visible execution context.

This boundary addresses conversational poisoning, rejected-draft contamination,
instruction competition, and response-plan anchoring. It is not a complete
security boundary and does not neutralize prompt injection contained in source
documents, websites, or tool results.

## Consequences

### Positive

- Execution begins with a compact, user-approved operative specification.
- Rejected requirements cannot influence the result merely by remaining nearby.
- Premature conclusions in abandoned plans cannot anchor analysis.
- More of the execution context is available for task inputs and substantive
  reasoning.
- The exact execution specification can be hashed, audited, and replayed.

### Negative

- A user-confirmed omission becomes authoritative and can propagate directly to
  the result.
- Required details are lost if the context compiler mistakes task data for
  discardable conversation.
- Audit storage and model-visible context must be maintained as separate
  concepts.
- Source-input prompt injection still requires ordinary trust and safety
  controls.

## Alternatives considered

### Continue the full conversation but label confirmed artifacts authoritative

Rejected as the target. Labels do not eliminate attention competition or
anchoring from obsolete text.

### Discard every original input after Prompt confirmation

Rejected. Confirmed Prompt Pseudocode governs semantics, but execution may still
need attached files, source documents, data, or other noninstructional inputs.

### Treat confirmation as a security approval

Rejected. Protocol confirmation approves semantic and procedural artifacts; it
does not bypass safety policy, permissions, or tool approvals.

