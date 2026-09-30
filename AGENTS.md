# Agent Rules & Guidelines

## Live Session REPL Verification Rule (CRITICAL / MANDATORY)
- Every completed pass (not necessarily mid-pass), you MUST test using the live session REPL in the test directory `C:\Users\USER\Desktop\Frameworks\PDLt-Test` using dev mode to confirm green.
- Run the REPL with `--dev` or `/dev on` to inspect telemetry, stage transitions, and deliverable correctness.
- This is the most important directive.

## PDL Standard Adherence
- Prompt Pseudocode MUST strictly conform to `PDL-01` through `PDL-08`.
- NO invented field schemas (`TASK:`, `OUTPUT:`, `INCLUDE:`).
- One operation per line (`PDL-02`), capitalized action verbs (`PDL-04`).
- No drafting meta-rules or deferrals in the prompt or plan bodies (`PROMPT-01`, `PDL-08`).

## Architecture & Verification Governance (ADR-0018, ADR-0019, ADR-0020)
- **Pydantic SSOT (ADR-0018)**: NEVER use heuristic regex for domain detection, witness extraction, or wire verification. All parsing and validation MUST go through strict, schema-first Pydantic models with alias coercion (`OutputVerifier`, `PartitionSumTriplesChecker`).
- **Autonomous Host Execution & First-Class Reasoning (GUARD-03)**:
  - When Python code or solver scripts are present, the host sandbox automatically executes them to capture stdout witnesses. NEVER emit `REQUEST_INPUT` asking the user to run code.
  - Analytical derivations, symbolic mathematics, word problems, and logical deductions are first-class deliverables (`GUARD-03`). The harness MUST NOT coerce symbolic or reasoning tasks into executable Python scripts or force models to fabricate concrete values for symbolic variables.
- **System 1 Boundary Refusal (ADR-0020, GUARD-02)**: Out-of-bounds, network-dependent, or mathematically impossible tasks MUST be intercepted and refused fail-closed by System 1 in <2s conditioned on runtime environment variables (`PDLT_SANDBOX_NETWORK`, `PDLT_POLICY_SCOPE`, `PDLT_KNOWLEDGE_CUTOFF`). NEVER hardcode prompt-specific benchmark tokens or entity names into production regex traps.
- **Headless Automation & Exit Codes (ADR-0019)**:
  - `0`: `CLOSED_SUCCESS` (deliverable verified).
  - `1`: `CLOSED_CANCELLED` / fail-closed error.
  - `2`: `UNCONFIRMED_GATE` (execution stalled at review gate).
  - `3`: `WAITING_INPUT` (legitimate pause awaiting external input).
- **Catalogue Verification**: When running tests in `C:\Users\USER\Desktop\Frameworks\PDLt-Test`, use `python catalogue-runs/run_catalogue.py --fail-fast` to ensure zero regressions across all 15 categories.

## Post-Implementation Anti-Overfitting & Integrity Gate (MANDATORY / SSOT)
- **The Referee Invariant (GUARD-01, GUARD-04)**: The harness is strictly an objective protocol referee and governor—NEVER an AI task solver. The harness MUST NEVER:
  - Inject prescriptive algorithmic advice, search methods (e.g. MRV, backtracking, DLX), or solution hints into prompts, plans, or `CARRIED_APPROACH_SOURCES`.
  - Mechanically require specific algorithmic keywords in Plan Soundness gates.
  - Scrape deliverable text with regex to synthesize witnesses.
- **Mandatory Anti-Overfitting Suite**: After ANY implementation round touching prompts, gates, checkers, or session engine, you MUST execute:
  ```bash
  pytest tests/test_harness_anti_overfitting.py
  ```
  Every test must pass with zero warnings, failures, or skips.
- **Guardrail Cross-Check**: Any changes MUST strictly conform to `docs/guardrails/ANTI_OVERFITTING_AND_BENCHMARK_INTEGRITY.md` (`GUARD-01` through `GUARD-05`).
- **Integrity Over Checkmarks**: **A failed benchmark is acceptable and diagnostic of genuine model capability boundaries (e.g. `REG-011`, `REG-012`), but a gamed benchmark is a critical integrity breach.** Never introduce harness crutches to force a green test.


