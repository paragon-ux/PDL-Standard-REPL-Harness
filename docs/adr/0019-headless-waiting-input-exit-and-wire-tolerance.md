# ADR-0019: Headless WAITING_INPUT Exit Code & Execution Wire Input Tolerance

**Status:** Accepted  
**Date:** 2026-09-29  
**Deciders:** PDL-Standard Architecture Team  
**Tracking Issue / Regression:** `REG-013` (Surfaced by `13-06 insufficient_information` in `catalogue-13-06-1790682691`)  

---

## Context

When an interactive prompt intentionally lacks necessary domain parameters (e.g. prompt `13-06`: database engine, table names, schema, query text, and performance constraints), the semantically sound model response is to request clarification rather than hallucinate parameters.

In the PDLt runtime:
1. The model properly completes `PROMPT_REVIEW` and `PLAN_REVIEW` indicating an intent to request missing details.
2. At `EXECUTE`, the model emits the native wire outcome:
   ```json
   {"kind": "REQUEST_INPUT", "body": "Please provide details...", "expected_type": "string"}
   ```
3. Prior to this ADR, two points of friction caused false-negative failures:
   * **Wire Schema Over-Constraining:** In `wire_payloads.py`, `ExecutionRequestInputData` strictly required a redundant `description` field with `extra="forbid"`. Omitting `description` triggered `WireError: missing_fields`, which on retry frequently produced malformed JSON.
   * **Headless REPL Exit Blindness:** When `REQUEST_INPUT` succeeded, `session_engine.py` called `self.controller.request_execution_input()`, correctly placing the controller into `Stage.WAITING_INPUT`. In non-interactive / headless test runs (`--non-interactive --exit-on-close`), `repl.py` blindly categorized any non-`CLOSED_SUCCESS` stage as an unconfirmed review gate failure (exit code 2).

A rejected alternative (Option B in `2026-09-29-request-clarification-routing-path.md`) proposed introducing a new controller stage `CLARIFICATION_REQUESTED`, bypassing `EXECUTE`, and classifying plan text using NLP action-verb parsers. That proposal was rejected because it violated multi-turn chaining (`session_engine.py` line 750), bypassed workspace turn archiving (ADR-0011 §2 in `workspace.py` line 577), violated the execution boundary (ADR-0004), and reintroduced heuristic NLP anti-patterns.

---

## Decision

1. **Contracts and Controller State Machine Remain Frozen:**
   * Normative contracts (`contracts/**/*`) remain positive-only and frozen.
   * `MechanicalController` state enums (`Stage`, `NextAction`, `Intent`) remain unchanged. `Stage.WAITING_INPUT` already exists as the authoritative, contract-compliant state for input requests.
2. **Pydantic Wire Tolerance for `REQUEST_INPUT`:**
   * In `wire_payloads.py`, `description` in `ExecutionRequestInputData` is made optional (`description: Optional[str] = None`).
   * When omitted or empty, an `after` model validator synthesizes a clean 1-line description from the first line of `body` (`body.strip().splitlines()[0][:120]`).
3. **Headless REPL Exit Code 3 (`WAITING_INPUT`):**
   * In `host/repl.py` (lines 1322–1341), if a non-interactive REPL session terminates with `final_stage == "WAITING_INPUT"`, the process prints:
     `[headless halt] Session paused at stage 'WAITING_INPUT' (input requested). Exiting (code 3).`
     and exits with code **`3`**.
   * Interactive REPL sessions remain completely unchanged, seamlessly waiting for operator input.
4. **Catalogue Scoring Realignment:**
   * `run_catalogue.py` maps exit code `3` to `verdict = "WAITING_INPUT"`.
   * For prompts where clarification is the ground truth (`13-06`), `CATALOGUE_MANIFEST.jsonl` specifies `"expected_stage": "WAITING_INPUT"`. When `verdict == expected_stage`, `run_catalogue.py` scores the run as a `PASS`.

---

## Consequences

### Positive
* **Zero Contract or Controller Mutations:** Zero risk of manifest hash divergence or state machine regressions.
* **Preserves Multi-Turn Continuity:** Multi-turn chaining and review routing in `session_engine.py` continue functioning without bricking.
* **Preserves Turn Archiving:** Conforms strictly to ADR-0011 §2 workspace lifecycle.
* **Single Source of Truth (SSOT):** No heuristic NLP parsers or action-verb whitelists; the model's typed execution outcome at `EXECUTE` is authoritative.
* **Accurate Benchmark Telemetry:** Clarification behavior is measured cleanly and distinguished from unconfirmed review gates.

### Tradeoffs
* Test harnesses and CI scripts inspecting REPL process return codes must recognize code `3` alongside `0`, `1`, and `2`.
