# Stage 30_plan

Job: Response Plan artifact production.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `DRAFT_PLAN`

- Layer 4 inputs: `CONFIRMED_PROMPT_BODY`, `CARRIED_APPROACH_SOURCES`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `RESPONSE_PLAN_ARTIFACT_BODY`

### `REVISE_PLAN`

- Layer 4 inputs: `CONFIRMED_PROMPT_BODY`, `CURRENT_PLAN_BODY`, `CARRIED_APPROACH_SOURCES`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `RESPONSE_PLAN_ARTIFACT_BODY`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
