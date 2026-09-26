# ADR-0002: Use controller-owned artifact controls

- Status: Accepted
- Date: 2026-08-06
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related requirements: [TRD-0001 Sections 7 and 8](../trd/0001-controller-gated-pseudocode-protocol.md#7-states-and-transitions)

## Context

The instruction-only skill asks the user to confirm or correct each artifact in
ordinary conversation. The model then infers whether the message is a
confirmation, correction, stop request, plan-only change, or semantic change.

Conversational confirmation is flexible, but it adds avoidable cognitive and
model burden:

- users must remember or compose an affirmative response;
- confirmation and correction can appear in the same message;
- the current state is implicit in conversation history;
- accidental phase advancement is possible;
- approach changes and request changes require model classification;
- confirmation chatter consumes context without contributing to the task.

The protocol has a small, finite state machine. These branches do not require
model judgment when the host can present explicit actions.

## Decision

The host controller SHALL own protocol branching and SHALL render each pending
artifact in a persistent, inspectable card or panel.

Prompt Pseudocode review SHALL provide:

- **Confirm interpretation**;
- **Revise interpretation**;
- **Stop**.

Response Plan Pseudocode review SHALL provide:

- **Confirm standard**;
- **Confirm pseudocode**;
- **Revise approach**;
- **Change request**;
- **Stop**.

Each action SHALL emit a typed controller event containing the protocol
instance, artifact identifier, and displayed version. The model SHALL receive
the instruction resulting from that event, not the user's button label as a
new conversational turn.

Revision SHALL accept inline feedback while keeping the current artifact
visible. The model SHALL regenerate the complete artifact. A diff or amendment
MAY be shown as secondary information but SHALL NOT replace the current complete
artifact.

During Plan review, **Revise approach** preserves the confirmed Prompt
Pseudocode. **Change request** invalidates the current plan and returns to Prompt
Pseudocode generation. This explicit branch is preferred to asking the model to
infer the user's intent from one undifferentiated correction action.

An event that contains both confirmation and revision feedback SHALL be treated
as revision. Silence SHALL never confirm an artifact.

Hosts without artifact UI MAY implement a text fallback, but the fallback SHALL
map input to the same controller events and state transitions.

## Consequences

### Positive

- Users recognize available actions instead of recalling confirmation phrases.
- Protocol state and available deviations are visible.
- Stale confirmations can be rejected deterministically.
- Semantic and plan-only revisions have explicit routes.
- Confirmation messages no longer pollute model context.
- State transitions become straightforward to test and audit.

### Negative

- The host must implement persistent components, accessible controls, and a
  fallback for clients without custom UI.
- Plan review exposes more actions than Prompt review and requires careful
  labeling.
- Explicit controls do not eliminate confirmation fatigue when the protocol is
  overused.

## Alternatives considered

### Require a magic confirmation token

Rejected. It simplifies parsing but increases recall burden and makes ordinary
conversation brittle.

### Keep natural-language confirmation only

Retained only as a compatibility fallback. It leaves deterministic branching
and state recovery to the model.

### Provide one generic Revise action during Plan review

Rejected as the preferred UI. It requires the model to decide whether feedback
changes the request or only the approach. The two explicit revision actions are
more predictable.

