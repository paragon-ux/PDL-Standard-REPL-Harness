# Implementation Plan: Substantive Correctness & Verification Architecture

> [!NOTE]
> **Archived Historical Planning Artifact:**
> This document is an unratified historical draft for `v2.4.2`. Its architectural objectives were formally superseded and shipped in `v2.5.0`–`v2.6.0` under [ADR-0013](../../adr/0013-substantive-correctness-verification.md) through [ADR-0020](../../adr/0020-system-1-environment-conditioned-refusal-routing.md), governed by [GUARD-01 through GUARD-05](../../guardrails/ANTI_OVERFITTING_AND_BENCHMARK_INTEGRITY.md). It is retained for provenance only.

- **Status:** ARCHIVED / HISTORICAL (Draft v2 targeting v2.4.2)
- **Target Version:** v2.4.2 (Shipped in v2.5.0–v2.6.0)
- **Related Decisions:** [ADR-0013](../../adr/0013-substantive-correctness-verification.md), [ADR-0014](../../adr/0014-dual-plane-boundary-and-wire-conformance.md)
- **Evidence Trace:** `session2-v-2-4-0.txt` (plan-soundness failure — no-backtrack greedy), `session9-v-2-4-0.txt` (witness/confabulation failure — correct answer, fabricated justification), `runs/live-sessions/session-20260927-052351/workspaces/.../turn_001/stages/50_execution/output/0004-execute/model-response.txt` (raw `result_ir` confirming the empty witness)

---

## 1. Executive Summary

Two failure modes, confirmed by two independent kinds of evidence,
neither fixed by the sys1/sys2 dialogue-governance work or by ADR-0014's
wire-shape validation:

- **A plan can be approved that is structurally incapable of a correct
  answer** (no-backtrack greedy scan against an adversarial instance) —
  a *before-execution* gap.
- **An answer can be correct on the surface and still ungrounded** — the
  Schur-triples "YES" was actually right, but with `result_ir.witness`
  absent, the very next turn asking "why" had nothing real to draw from
  and fabricated a derivation. This was confirmed directly from the raw
  execution payload, not inferred — a *retrieval* gap layered on a
  *retention* gap.

This plan closes both, in five parts (P0–P4), each independently testable
and gated behind a single classification flag so ordinary requests are
unaffected.

---

## 2. Component Map (real paths)

```
src/pdl_taskmaster/
├── providers/
│   ├── sys1/
│   │   └── recipes/
│   │       ├── problem_class.py        # NEW — P0 classification
│   │       └── plan_soundness.py       # NEW — P0 plan-time gate
│   ├── sys2/                            # unchanged
│   └── api_worker.py                    # EXTEND — verify-and-retry orchestration (P2)
├── runtime/
│   ├── wire_payloads.py                 # EXTEND — ResultIRPayload.witness (P1)
│   ├── session_engine.py                # EXTEND — witness projection into REQUIRED_TASK_INPUTS (P3)
│   └── operation_bridge.py              # unchanged, referenced for stage transitions
└── verification/                        # NEW package
    ├── __init__.py
    ├── sandbox.py                       # NEW — P1 OS-native execution sandbox (Windows Job Objects / setrlimit)
    ├── output_verifier.py               # P3 — deterministic checker dispatch
    └── checkers/
        ├── base.py                      # Checker protocol
        ├── partition_sum_triples.py     # first concrete checker
        └── fallback.py                  # P5 — provisional-label fallback

tests/
├── test_plan_soundness.py               # NEW
├── test_sandbox.py                      # NEW — OS-native sandbox containment, memory cap, and timeout tests
├── test_output_verifier.py              # NEW
├── test_witness_projection.py           # NEW
└── test_wire_repairs.py                 # EXTEND — verifier failures share the existing repair-attempt counter
```

> The exact current shape of `ResultIRPayload` wasn't visible from the
> transcript review — the schema below is reconstructed from the observed
> JSON (`files`, `reconciliation`, `open_defects`, each entry carrying an
> `evidence.path`). Reconcile field types against the real class before
> implementing.

---

## 3. P0 — Plan-Time Execution Commitment

**`problem_class.py`** (sys1 recipe, runs at prompt interpretation):
classifies `requires_verified_execution: true | false | review` using the
same criteria as v1 (existence/assignment/cover/matching questions, or
requests for an exact/optimal solution with a checkable witness).

**`plan_soundness.py`** (deterministic, harness-level — not a sys1
classification call): gates the transition into the execution stage.
Runs on the Response Plan text once after sys2 drafts it and again after
user confirmation.

Checks, unchanged in substance from v1, restated against real staging:

1. **Deferral check** — reject deferral markers ("deferred to execution",
   "TBD", "left to execution") without an accompanying concrete method.
2. **Completeness declaration** — the plan must commit to either (a) real
   code execution implementing exhaustive/backtracking search, or (b) a
   named heuristic with an explicit disclosure that a `NO` from it is not
   proof of non-existence. An undisclosed single-pass scan fails this.

On failure: return to sys2 with the specific criterion violated, capped
at `MAX_PLAN_REDRAFTS` (default 2), then surface the failure to the user
directly rather than looping.

This check must complete, pass or fail, **before** the run tree's
`.../stages/50_execution/` stage is entered — confirmed from the observed
run-tree layout (`turns/turn_001/stages/50_execution/output/0004-execute/model-response.txt`).

---

## 4. P1 — Bidirectional Witness (`wire_payloads.py`)

```python
from typing import Literal, Union
from pydantic import BaseModel

class Evidence(BaseModel):
    path: str  # e.g. "execution://witness", matches existing evidence.path convention

class PositiveWitness(BaseModel):
    polarity: Literal["positive"] = "positive"
    evidence: Evidence
    data: dict  # e.g. {"triples": [[12, 97, 109], ...]}

class NegativeWitness(BaseModel):
    polarity: Literal["negative"] = "negative"
    evidence: Evidence
    search_exhausted: bool
    nodes_explored: int
    method: str  # e.g. "backtracking_mrv"

class ResultIRPayload(BaseModel):
    files: list[FileEntry]              # existing
    reconciliation: list[ReconEntry]    # existing
    open_defects: list[Defect]          # existing
    witness: Union[PositiveWitness, NegativeWitness, None] = None  # NEW
```

Observed baseline this extends (raw payload for `session-20260927-052351`,
turn 1):

```json
{
  "kind": "RESULT",
  "body": "YES",
  "result_ir": {
    "files": [{"filename": "result.txt", "satisfies": ["R1"],
               "evidence": {"path": "execution://body"}}],
    "reconciliation": [{"requirement": "R1", "status": "satisfied",
                         "evidence": {"path": "execution://body"}}],
    "open_defects": []
  }
}
```

With P1 in place, that same turn's `result_ir.witness` would carry the
actual 15 triples (positive case) — the thing that was missing and whose
absence made the turn-2 confabulation structurally inevitable.

---

## 5. P2 — Mechanical, Bounded Verification (`output_verifier.py` + `api_worker.py`)

```python
def _execute_with_verification(
    self, plan: str, context: dict, problem_class: ProblemClassResult
) -> WorkerResult:
    if not problem_class.requires_verified_execution:
        return self._execute(plan, context)

    diagnostic = None
    for attempt in range(1, MAX_VERIFY_RETRIES + 1):
        result = self._execute(plan, {**context, "diagnostic": diagnostic})
        verdict = self.output_verifier.check(result.result_ir.witness, context["constraints"])
        if verdict.valid:
            return result
        diagnostic = verdict.diagnostic
        logger.info("Verify failed %d/%d: %s", attempt, MAX_VERIFY_RETRIES, diagnostic)

    return WorkerResult.unverified(
        message=f"No verified answer after {MAX_VERIFY_RETRIES} attempts. "
                f"Last failure: {diagnostic}"
    )
```

- Positive witness: independently re-check `data` against the literal
  input and constraints — disjointness, full coverage, `a + b == c` per
  triple for the partition-sum-triples checker.
- Negative witness: require `search_exhausted == true`; a `NO` without it
  is `status: unverified`, not final.
- **Retry budget:** route through the same bounded repair-attempt
  mechanism already exercised in `test_wire_repairs.py` rather than a
  second, independently-unbounded loop — confirm in code review whether
  wire-shape repairs and semantic-verify failures should share one
  counter or two; either is fine as long as both are bounded and both
  terminate in an explicit message, not a silent retry-forever or a
  silent fallback to the unverified candidate.

---

## 6. P3 — Grounded-Only Introspection (`session_engine.py`)

The Cumulative Turn Ledger already retains cross-turn context (this is
working correctly as of `session9-v-2-4-0.txt` — the 45-number list
wasn't re-requested). Extend it to project `result_ir.witness` into
`REQUIRED_TASK_INPUTS` whenever a later turn is classified as
introspection ("show your work", "why", "explain the last step").

The introspection-turn instruction template must state explicitly: cite
only the projected witness data; if the field is empty or absent, say so
plainly and stop there. This is a stated constraint on the turn's
instructions, not an assumption that data availability alone prevents
embellishment — the turn should be testable independent of whether the
witness happens to be populated.

---

## 7. P4 — Regression Fixtures & Fallback Checker

- **Primary fixture:** `session9-v-2-4-0.txt` — a correct headline answer
  followed by a fabricated justification is a stronger regression target
  than an outright wrong answer, and is the one to assert against first.
- **Secondary fixture:** `session2-v-2-4-0.txt` — the deferred-plan and
  no-backtrack-greedy text, for P0.
- **Live/manual case:** the 45-integer / N=15 adversarial instance (146
  candidate triples, 15 forming the true partition) — kept as a standing
  QAT case because a plan without real search will fail it.
- **`checkers/fallback.py`:** for any `requires_verified_execution`
  request with no registered domain checker, label the result
  `"provisional"` rather than passing it through as verified.

---

## 8. Phased Rollout

- **Phase A:** P0 (`problem_class.py`, `plan_soundness.py`) + fixtures
  from `session2-v-2-4-0.txt`.
- **Phase B:** P1 (`ResultIRPayload.witness`) — schema only, no
  enforcement yet, so existing flows are unaffected while the field beds
  in.
- **Phase C:** P2 (`output_verifier.py`, `partition_sum_triples.py`
  checker, retry wiring in `api_worker.py`).
- **Phase D:** P3 (`session_engine.py` projection + introspection
  instruction constraint).
- **Phase E:** P4 fixtures wired into the test battery + fallback
  checker; full regression against the existing suite; User QAT re-run
  of both `session2-v-2-4-0.txt` and `session9-v-2-4-0.txt` end to end.
