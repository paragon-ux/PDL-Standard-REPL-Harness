# Stage 40_plan_review

Job: Response Plan review interpretation.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `INTERPRET_PLAN_REVIEW`

- Layer 4 inputs: `BOUND_REVIEW_SUBJECT_KIND`, `BOUND_REVIEW_SUBJECT_BODY`, `RAW_USER_REVIEW_MESSAGE`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `ARTIFACT_REVIEW_FACTS`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
