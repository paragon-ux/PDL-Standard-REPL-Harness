# ADR-0010: Pydantic Schema Enforcement and Structured Wire Contracts

- Status: Accepted
- Date: 2026-09-26
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0002](0002-controller-owned-artifact-controls.md), [ADR-0003](0003-phase-projected-single-model-contexts.md), [ADR-0006](0006-bounded-pre-execution-reasoning.md)
- Related requirements: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md), [TRD-0003](../trd/0003-result-pseudocode-decomposition-standard.md)

## Context

In earlier iterations of the harness, model responses from semantic worker invocations (`scripts/runtime/operation_bridge.py`) were validated via ad-hoc, placement-tolerant JSON extraction (`_object()`) and manual dictionary inspection (`_keys()`). Each operation parser manually asserted key presence, checked primitive types, and raised string-keyed `WireError` exceptions (e.g. `WireError("extra_fields")`, `WireError("invalid_json")`).

This approach has reached its maintainability and reliability limit:
1. **Validation Fragmentation:** Output schemas are maintained redundantly across `contracts/EXECUTION_CONTRACT.json`, `contracts/VERIFICATION_CONTRACT.json`, provider grammar sanitizers (`_sanitize_schema_for_grammar`), and runtime parser functions in `operation_bridge.py`.
2. **Coarse Error Feedback:** When a model generates malformed output or drops a required field, the retry-once loop in `SessionEngine._call` relies on a generic operator correction message (`OPERATOR CORRECTION: the previous response failed host-side validation...`). It lacks fine-grained field-level localization to explain precisely which attribute violated the contract.
3. **Provider Grammar Disconnect:** Structured output APIs (e.g. OpenAI/OpenRouter `text.format.json_schema`) require valid, context-free JSON Schemas. Manually handcrafted JSON schemas frequently drift from Python parser logic.

## Decision drivers

- Unify wire deserialization, field validation, and contract typing into a single, high-performance schema authority.
- Provide automated, exact operator correction feedback on wire validation failures for the retry-once mechanism.
- Directly emit strict JSON Schema definitions via `model_json_schema()` to drive `--api-structured-output` without redundant contract files.
- Preserve placement tolerance (handling markdown fences, BOM markers, and leading/trailing chatter) while guaranteeing strict internal field typing.

## Decision

The harness SHALL adopt **Pydantic v2** as the exclusive schema enforcement layer across `OperationBridge` and model request/response boundaries:

### 1. Strongly Typed Wire Payloads
Every semantic operation output SHALL be modeled as a Pydantic `BaseModel` with strict field constraints, replacing custom dataclasses and dictionary parsing:
- `ActivationDecisionPayload`: Enforces valid `ActivationRoute` enums and non-empty responses on higher-priority blocks.
- `BootstrapAnalysisPayload`: Enforces string requirements for `task_summary`, `approach_notes`, `risk_notes`, and verbatim `task_entities` list parsing.
- `PromptDraftPayload`: Discriminated union handling `kind="PROMPT"` (with `approach_handoff` enum validation) and `kind="TASK_BLOCKED_BY_HIGHER_PRIORITY"`.
- `ReviewFactsPayload`: Validates `task_change_dimensions` and `approach_change_dimensions` against ratified normative subsets with deduplication assertions, plus boolean `progression_requested`.
- `ExecutionDraftPayload` & `ExecutionOutcomePayload`: Validates delivery markers, typed execution entities, and optional nested `ResultIRPayload` structures per TRD-0003.

### 2. Single Source of Truth for Structured Output Grammars
- Provider-level JSON Schemas passed to `--api-structured-output` SHALL be dynamically derived via `PayloadModel.model_json_schema()`.
- State-dependent or context-free incompatible schema keywords (`uniqueItems`) SHALL be stripped deterministically at the provider bridge level, ensuring universal compatibility across vLLM, SGLang, and OpenRouter endpoints.

### 3. Precision Operator Corrections
- When model deserialization fails a Pydantic contract, `SessionEngine._call` SHALL format `ValidationError.errors()` into explicit, field-localized operator correction prompts:
  ```text
  OPERATOR CORRECTION: Validation failed on field 'task_entities': expected list[str], got string.
  Emit exactly one conforming JSON object matching the declared schema.
  ```
- This eliminates ambiguity during the retry-once cycle and significantly reduces repeat wire failures.

## Consequences

### Positive
- Replaces hundreds of lines of fragile manual dict/type assertion boilerplate in `scripts/runtime/operation_bridge.py`.
- Eliminates schema drift between runtime Python code and static JSON contract definitions.
- Generates precise, automated operator retry instructions that increase recovery rates on sampling glitches.

### Neutral / Negative
- Introduces an explicit dependency on `pydantic>=2.0.0` (already installed in the environment).
- Serialization/deserialization benchmarks must be monitored to ensure negligible latency overhead (Pydantic v2's Rust core delivers sub-millisecond validation).
