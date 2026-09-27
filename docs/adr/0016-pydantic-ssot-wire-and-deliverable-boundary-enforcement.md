# ADR-0016: Pydantic Single Source of Truth (SSOT) for Wire and Deliverable Boundary Enforcement

- Status: Accepted
- Date: 2026-09-27
- Parent decisions: [ADR-0010](0010-pydantic-wire-enforcement.md), [ADR-0014](0014-dual-plane-boundary-and-wire-conformance.md)
- Related decisions: [ADR-0009](0009-result-pseudocode-decomposition-standard.md), [ADR-0013](0013-substantive-correctness-verification.md), [ADR-0015](0015-model-synthesized-verification-and-confinement-boundaries.md)
- Related standards: [RESULT_STANDARD](../../contracts/standards/RESULT_STANDARD.md), [EXECUTION_CONTRACT](../../contracts/EXECUTION_CONTRACT.json)

## Context

In early iterations of Protocol v2 and the Result Pseudocode decomposition standard (TRD-0003, ADR-0009), Result IR validation was fragmented across two distinct evaluation paths:
1. **Procedural Checking in `result_ir.py`:** Markdown-extracted Result IR blocks were validated by hand-coded procedural loops checking dictionary keys, array types, and string constraints.
2. **Weak Wire Typing in `wire_payloads.py`:** Wire-level `ResultIRData` used `list[Any]` for `files`, `reconciliation`, and `open_defects`, validating only the top-level keys and the optional `witness` sub-schema.

This fragmentation caused three architectural regressions in live testing:
* **Validation Asymmetry:** Wire payloads were validated by Pydantic, but canonical markdown deliverables (`RS-01`) bypassed Pydantic entirely. Structural errors were reported in inconsistent formats depending on whether the payload arrived via the wire or via deliverable text.
* **Top-Level Wire Collision:** Under structured output or direct worker execution, language models frequently emit the Result IR JSON object directly at root (`{"files": [...], "reconciliation": [...], "witness": {...}}`). Because `ExecutionOutcomePayload` was an unconditioned discriminated union requiring `"kind": "RESULT"`, Pydantic rejected the response with `WireError: execution_kind`. On retry, models panicked, stripped their computed code, and emitted empty or speculative negative results.
* **Diagnostics Precedence Inversion:** Semantic checks (e.g. workspace file resolution, verbatim substring searching) frequently executed before structural wire validation had confirmed that fields conformed to schema types.

## Decision

The harness establishes **Pydantic as the Single Source of Truth (SSOT)** for all structural validation across both wire protocols and deliverable artifacts.

### 1. Unified Pydantic Result IR Schema Hierarchy
All Result IR components are codified into immutable, strongly typed Pydantic models in `src/pdl_taskmaster/runtime/wire_payloads.py`:
* **`Evidence`:** Path, optional section marker, and optional verbatim quote.
* **`FileItem`:** Filename, satisfies requirement list, and evidence citation.
* **`ReconciliationItem`:** Requirement identifier (`R<n>`), status enum (`satisfied`, `partial`, `open`), and evidence citation.
* **`DefectItem`:** Defect identifier (`D<n>`), description, and evidence citation.
* **`ResultIRData`:** Complete Result IR object containing typed lists of `FileItem`, `ReconciliationItem`, `DefectItem`, and discriminated `Union[PositiveWitness, NegativeWitness]`.

### 2. Pydantic-First Enforcement Sequence
Structural validation MUST precede semantic evaluation in all phases:
1. **Phase 1 (Pydantic Structural Enforcement):** Any candidate Result IR (whether from the wire or extracted from markdown fences) MUST first be validated via `ResultIRData.model_validate(raw_ir)`.
   - If Pydantic validation fails, the validation pipeline immediately halts and returns field-localized, formatted Pydantic errors.
   - Hand-coded structural checks are retired in favor of the declarative Pydantic model.
2. **Phase 2 (Host Semantic Verification):** Only after Pydantic confirms schema conformance does the host perform semantic verification:
   - Workspace file path resolution (boundary escape checks).
   - Verbatim section and observation quote containment checks.
   - Requirement coverage and 1-to-1 bijection against confirmed prompt requirements.
   - Substantive domain witness verification (ADR-0013 / ADR-0015).

### 3. Root Result IR Wire Normalization
To prevent false-positive `execution_kind` rejections when models emit a bare Result IR JSON object, `ExecutionOutcomePayload` introduces pre-validation normalization:
* If an incoming JSON object contains Result IR hallmarks (`"files"` or `"reconciliation"`) without a `"kind"` discriminator, the validator automatically wraps it into a canonical `ExecutionResultData` outcome:
  ```json
  {
    "kind": "RESULT",
    "body": "<serialized delivery text>",
    "result_ir": <original object>
  }
  ```
* This maintains wire integrity without destabilizing model context during execute retries.

## Consequences

### Positive
- **Single Source of Truth:** One declarative schema (`ResultIRData`) defines and validates Result IR across wire, repair, and markdown channels.
- **Fail-Fast Structural Diagnostics:** Structural errors produce deterministic, localized feedback before expensive host semantic checks or sandbox execution runs.
- **Robustness Against Model Formatting Variance:** Direct JSON emissions are preserved rather than rejected by discriminator mismatches.
- **Strict ADR-0014 Compliance:** Normative drafting discipline and wire conformance remain cleanly separated.
