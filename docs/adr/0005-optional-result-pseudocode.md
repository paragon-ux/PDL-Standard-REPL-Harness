# ADR-0005: Support optional Result Pseudocode

- Status: Accepted
- Date: 2026-08-06
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related requirements: [TRD-0001 Sections 8.3 and 10.3](../trd/0001-controller-gated-pseudocode-protocol.md#83-plan-review-controls)

## Context

The original protocol uses pseudocode only as a temporary interpretation and
planning interface. After both artifacts are confirmed, the model returns a
standard final response.

Some users will want the executed result itself as pseudocode. A persistent
pseudocode result can serve as a reusable intermediate representation for:

- continued planning and later execution;
- deterministic workflow input;
- dry-run and regression evaluation;
- comparison of prompt and plan variants;
- selectively retrieved few-shot examples;
- task decomposition or downstream automation.

Response Plan Pseudocode cannot serve this purpose because it intentionally
contains no findings, selected alternatives, resolved values, or completed
answer.

## Decision

Plan review SHALL offer two confirmation events:

- **Confirm standard** executes the confirmed pair and returns the task's
  ordinary output form.
- **Confirm pseudocode** executes the same confirmed pair and returns Result
  Pseudocode.

The output-mode choice is a controller-owned rendering parameter predeclared by
the protocol. Selecting it does not change task semantics and therefore does
not return to Prompt review. If the user also changes required content, scope,
audience, constraints, or deliverable characteristics, the semantic change
SHALL return to Prompt review.

Result Pseudocode SHALL:

- contain the substantive executed result;
- preserve the content required by confirmed Prompt Pseudocode;
- follow the confirmed high-level approach;
- use the existing Cal Poly PDL conventions;
- contain resolved conclusions, values, choices, or procedures when the task
  requires them;
- remain distinguishable from a response plan by its completed content rather
  than invented syntax or schema labels.

The executor SHOULD generate Result Pseudocode directly. It SHOULD NOT first
produce a complete natural-language answer and then perform an unconstrained
rewrite, because that adds cost and can alter meaning.

Result Pseudocode SHALL remain optional. When a required native artifact cannot
be faithfully represented as PDL, the system SHALL preserve the native artifact
alongside an appropriate PDL result or report the incompatibility. It SHALL NOT
silently discard required content to force pseudocode representation.

Every Result Pseudocode artifact SHALL retain provenance linking it to the
confirmed Prompt and Plan versions, output mode, model configuration, and
required source inputs.

## Consequences

### Positive

- Pseudocode becomes a reusable result artifact rather than only a transient
  confirmation aid.
- Prompt, Plan, and Result triples support evaluation and replay.
- The same controller can automate dry runs and compare phase configurations.
- Users can continue from a resolved procedural representation.

### Negative

- Not every answer is naturally algorithmic or procedural.
- Result Pseudocode requires separate validation from Prompt and Plan artifacts.
- Users may confuse a plan with a result unless the UI and content are clear.
- Direct PDL rendering can reduce readability for prose-oriented tasks.

## Alternatives considered

### Always return Result Pseudocode

Rejected. It would degrade tasks whose native result is prose, a table, media,
code, or another specialized artifact.

### Rewrite every standard response into pseudocode afterward

Rejected as the preferred path. It doubles generation work and introduces a
semantic transformation after execution.

### Put findings into Response Plan Pseudocode

Rejected. It would poison the plan by collapsing intended procedure and
substantive result.

