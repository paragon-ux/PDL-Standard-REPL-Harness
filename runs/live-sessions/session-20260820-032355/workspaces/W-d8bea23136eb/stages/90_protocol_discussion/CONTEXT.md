# Stage 90_protocol_discussion

Job: Bounded protocol discussion.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `ANSWER_PROTOCOL_DISCUSSION`

- Layer 4 inputs: `RAW_PROTOCOL_QUESTION`, `CURRENT_STAGE_CLASS`, `BOUND_REVIEW_SUBJECT_KIND`, `BOUND_REVIEW_SUBJECT_BODY`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `PROTOCOL_DISCUSSION_RESPONSE`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
