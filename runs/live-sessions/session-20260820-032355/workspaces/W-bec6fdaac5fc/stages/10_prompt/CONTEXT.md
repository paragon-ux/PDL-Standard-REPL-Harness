# Stage 10_prompt

Job: Prompt artifact production.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `DRAFT_PROMPT`

- Layer 4 inputs: `HOST_PROTOCOL_STATE`, `SUBSTANTIVE_REQUEST`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `PROMPT_DRAFT_OUTCOME`

### `REVISE_PROMPT`

- Layer 4 inputs: `CURRENT_PROMPT_BODY`, `TASK_CHANGE_SOURCE`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `PROMPT_ARTIFACT_BODY`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
