# Stage 00_activation

Job: Activation routing.

This Layer 2 contract is non-normative. It declares context routing only; applicable
requirement IDs are resolved to clause text from the sole Standard source at runtime.

## Operations

### `INTERPRET_ACTIVATION`

- Layer 4 inputs: `RAW_USER_MESSAGE`
- Layer 3 requirement IDs: `references/operation-bindings.json`
- Output kind: `ACTIVATION_DECISION`

## Handoff

Each invocation materializes its declared Layer 4 inputs under `input/<invocation>/` and
records the compiled projection plus model output under `output/<invocation>/`.
Prompt, Plan, and execution stages additionally publish explicit current working artifacts
that later selected stages consume as filesystem handoffs.
