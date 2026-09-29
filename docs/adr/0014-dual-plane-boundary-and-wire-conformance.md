# ADR-0014: Dual-Plane Boundary Architecture for Normative Standards and Wire Conformance

- Status: Accepted
- Date: 2026-09-27
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), [ADR-0007](0007-operationalize-negative-constraints-by-omission.md), [ADR-0010](0010-pydantic-wire-enforcement.md)
- Related standards: [PDL_STANDARD](../../contracts/standards/PDL_STANDARD.md), [PROMPT_STANDARD](../../contracts/standards/PROMPT_STANDARD.md), [RESPONSE_PLAN_STANDARD](../../contracts/standards/RESPONSE_PLAN_STANDARD.md)

## Context

During early live REPL testing of Protocol v2 (Sessions 5 through 7), the harness exhibited a subtle, recurring failure mode during prompt and response plan drafting:
1. **Semantic Plane Collision:** Two independent layers of constraints collided in the model's generation context:
   - **The Specification Plane (`TASK-01` / Object Level):** What the target deliverable must compute and deliver upon execution (e.g. partition the string into palindromes with minimum cuts).
   - **The Drafting Discipline Plane (`PROTO-03`, `PROMPT-02`, `PLAN-04` / Meta Level):** Procedural rules governing the agent's behavior during a review gate (e.g. do not solve the substantive problem prematurely during prompt drafting).
2. **Negative Priming:** When the worker prompt instructed the LLM with negative prohibitions (e.g. *"NEVER add negative meta-constraints like 'do not compute' or 'describe only'"*), the LLM suffered from negative priming. It interpreted the operational drafting instruction as an operative constraint on the task itself, emitting:
   ```text
   TASK: Partition string. OUTPUT: Return partition. INCLUDE: Input "...". DO NOT perform the partitioning; only describe the required result.
   ```
3. **Flawed Mitigation via Post-Hoc Heuristics:** The runtime originally attempted to filter these hallucinations using post-hoc regex string-stripping (`_strip_meta_rule_bleed`) in `operation_bridge.py`. This heuristic approach proved brittle:
   - It only matched specific line-initial patterns, failing when models varied sentence structure or inlined multiple statements on a single line.
   - It silently masked underlying schema invalidity (`PDL-05` fielded schema violations like `TASK:`, `OUTPUT:`) instead of signaling contract non-conformance.
   - When text slipped past the regex, `AUTH-03` detected the prohibited text in the confirmed prompt, forcing the response plan into inserting dummy placeholders (`STEP 3: INSERT placeholders for the substantive results without performing any computation`), ultimately causing the execution stage to return empty results.

## Decision Drivers

- Enforce complete plane isolation: operational drafting discipline must never contaminate substantive task requirements.
- Eliminate negative priming across worker prompt construction.
- Elevate contract compliance (`PDL-01` through `PDL-08`, `PROMPT-01` through `PROMPT-05`, `PLAN-01` through `PLAN-10`) to the Pydantic wire schema boundary, abandoning post-hoc regex stripping.
- Provide a standardized protocol for modifying or adding normative clauses without destabilizing the runtime balance.
- Maintain rapid recovery via automated, localized `OPERATOR CORRECTION` retry loops.

## Decision

The harness adopts the **Dual-Plane Boundary Architecture**, governing normative standards authoring, provider prompt generation, and wire schema validation.

### Pillar 1: Grammatical Inversion (Positive Structural Shapes Over Negative Taboos)
- **Normative Standards & Worker Guidance:** All operational drafting guidelines in `api_worker.py` and normative standards in `contracts/standards/` SHALL be phrased **positively as required structural shapes and concrete exemplars**, never as negative taboos.
- **Strict Prohibition on Negative Priming:** Instructions SHALL NOT tell the model what words to avoid (e.g. *"do not say 'do not compute'"*), as this primes language models to emit synonymous variations.
- **Standard Positive Template:**
  ```text
  1. Express the prompt in clean Structured English using uppercase action verbs (PDL-01, PDL-04).
     Example format:
     PARTITION the input string into palindrome substrings where each character belongs to exactly one palindrome
     MINIMIZE the number of cuts in the resulting partition
     RETURN the minimum-cut partition and cut count
  2. Layout: Each distinct operation or requirement MUST appear on its own line (PDL-02).
  3. No Invented Field Schemas: DO NOT use fielded prefixes like 'TASK:', 'OUTPUT:' (PDL-05). State each operation directly.
  4. Purpose-Complete Target: Prompt Pseudocode defines the substantive requirements to be solved upon execution (PROMPT-01).
  ```

### Pillar 2: Wire-Level Contract Enforcement (Fail-Fast at Pydantic Boundary)
- **Pydantic as the Single Source of Truth:** `PromptDraftData`, `PromptBodyPayload`, and `NeutralPlanBodyPayload` in `src/pdl_taskmaster/runtime/wire_payloads.py` SHALL validate contract adherence at schema instantiation time via Pydantic model validators:
  - **`PDL-05` Enforcement:** Rejects fielded prefixes (`TASK:`, `OUTPUT:`, `INPUT:`, `INCLUDE:`, `ACTION:`, `RESULT:`, `STATUS:`) whether at line starts or inlined.
  - **`PDL-08` / `PROMPT-01` Enforcement:** Rejects meta-rule bleed, drafting commentary, or negative computation prohibitions (`DO NOT perform...`, `only describe the required result`, `without performing any computation`, `defer computation`).
  - **`PLAN-04` / `PLAN-10` Enforcement:** Rejects response plan placeholder steps (`INSERT placeholders for the substantive results...`) and computation deferrals.
- **Abolition of Silent Post-Hoc Stripping:** The runtime SHALL NOT silently mutate, strip, or rewrite model outputs to make invalid payloads appear valid. Non-conforming payloads MUST raise `ValidationError`.
- **Mechanical Self-Correction:** When Pydantic raises a `ValidationError`, `OperationBridge._validate` maps the failure to a canonical `WireError` token (`prompt_pdl_field_schema_prohibited`, `prompt_pdl_meta_rule_bleed`, `plan_pdl_placeholder_bleed`) with field-localized operator feedback. `SessionEngine._call` automatically sends the operator correction back to the worker for a single retry.

### Pillar 3: The Tripartite Clause Contract
To guarantee that future edits to normative clauses do not re-introduce regressions or plane leakage, any modification to clauses in `contracts/standards/` MUST satisfy three coordinated requirements:
1. **Normative Definition:** Defined in `contracts/standards/*.md` with explicit RFC 2119 keywords (`MUST`, `SHOULD`, `MUST NOT`).
2. **Positive Exemplar:** An unambiguous positive exemplar added to `api_worker.py` operational guidelines.
3. **Counter-Exemplar Validator & Test:** An explicit regex/validator added to `wire_payloads.py` paired with a unit test in `tests/test_wire_repairs.py` verifying that:
   - The anti-pattern raises `WireError` with the exact clause citation.
   - The emitted `operator_feedback` guides the model to the valid positive structure.

### Pillar 4: Schema Grammar Sanitization for Provider Interoperability
- **Provider-Agnostic JSON-Schema Sanitization:** `ApiWorker._sanitize_schema_for_grammar` recursively inlines all `$defs` and `$ref` pointers into self-contained JSON schema definitions, stripping unsupported keywords (`$schema`, `title`, `description`, `minLength`, `maxLength`, `minItems`, `maxItems`, `uniqueItems`), converting `const` into single-item `enum` constraints, and enforcing `additionalProperties: false` for object schemas.
- **Strict Decoding Engine Compatibility:** Ensures that Pydantic-derived wire schemas function seamlessly across strict backend grammar engines (such as Groq, vLLM, Venice, Outlines, and Vertex) without triggering upstream JSON validation 400/500 transport errors.

## Regression Guardrails

1. **Schema Boundary Regression Suite:** `tests/test_wire_repairs.py` SHALL maintain parameterized tests asserting that all historical failure shapes (Session 7 Run 2 inlined fields, embedded meta-rule bleed, and plan placeholder steps) are rejected deterministically by Pydantic.
2. **Live REPL Verification & Environment Mirroring Directive:** Per `AGENTS.md` and ADR-0015, every completed pass SHALL execute a live test using the REPL in `C:\Users\USER\Desktop\Frameworks\PDLt-Test` with `--dev` mode enabled. To prevent provider-specific schema validation regressions (such as Groq transport errors), the live test pass MUST mirror the target deployment environment (model, base URL, and decoding parameters) across all operational stages (`PROMPT_REVIEW` → `PLAN_REVIEW` → `CLOSED_SUCCESS`).

## Consequences

### Positive
- Completely resolves prompt flakiness and negative priming across models.
- Guarantees strict adherence to `PDL-01` through `PDL-08`, `PROMPT-01` through `PROMPT-05`, and `PLAN-01` through `PLAN-10`.
- Protects the execution stage from empty deliverables caused by accidental computation prohibitions.
- Preserves sub-second to 2-second turnaround latencies by eliminating multi-retry confusion.

### Neutral / Negative
- Adding or revising a normative standard requires updating both the Pydantic validator in `wire_payloads.py` and the positive guidance in `api_worker.py`.
- Models that persistently fail to generate valid PDL after retry will fail-closed with a `WireError`, surfacing the defect immediately rather than silently proceeding with corrupt state.
