# Stage 50_execution

Job: Execution and execution-input continuation.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `EXECUTE`

- Layer 4 inputs: `CONFIRMED_PROMPT_BODY`, `CONFIRMED_PLAN_BODY`, `REQUIRED_TASK_INPUTS`, `SUPPLIED_EXECUTION_INPUT_SOURCE`, `AVAILABLE_EXECUTION_TOOLS`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `EXECUTION_OUTCOME`

### `INTERPRET_EXECUTION_INPUT`

- Layer 4 inputs: `BOUND_REVIEW_SUBJECT_KIND`, `BOUND_REVIEW_SUBJECT_BODY`, `RAW_USER_REVIEW_MESSAGE`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `EXECUTION_INPUT_DECISION`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
