# TRD-0003: Result Pseudocode Decomposition Standard with Mechanically Validated Evidence Citations

- Status: Proposed (prototype-implemented; feature-gated)
- Version: 0.9
- Date: 2026-09-18
- Parent decisions:
  - [ADR-0009: Require decomposed Result Pseudocode with cited execution evidence](../adr/0009-result-pseudocode-decomposition-standard.md)
  - [ADR-0005: Support optional Result Pseudocode](../adr/0005-optional-result-pseudocode.md)
- Related requirements:
  - [TRD-0002: Controller-Gated Pseudocode Protocol](0002-controller-gated-pseudocode-protocol.md)
- Governing decisions:
  - [ADR-0003: Use phase-projected single-model contexts](../adr/0003-phase-projected-single-model-contexts.md)
  - [ADR-0004: Make confirmed artifacts the clean execution boundary](../adr/0004-confirmed-artifacts-as-execution-boundary.md)
  - [ADR-0008: Context, session, and normative storage architecture](../adr/0008-context-and-session-management.md)
- Empirical foundations: live build sessions `runs/wal-build`, `runs/wal-exp2b`, `runs/wal-exp4`
  (cross-epoch API hallucination eliminated by native chaining; residual wandering eliminated by
  reconciled decomposition; hallucinated expectations structurally invalid without citations).

## 1. Purpose and scope

This standard defines the **Result Pseudocode decomposition IR** ("Result IR"): the
structured, reconciled, evidence-cited form that the EXECUTE operation emits alongside
the native deliverable, and the mechanical duties of the controller when validating,
publishing, and chaining it.

Motivation (measured): phase-projected contexts launder source material out of the
execution projection (ADR-0003 inclusion lists). Byte-exact native chaining alone
restores API fidelity but does not steer revision epochs (the executor re-architects
unconstrained components). A dense, approach-invoking IR that is *co-referential with
the confirmed Prompt Pseudocode* and *grounded in resolvable evidence* supplies the
missing steering signal. Neither representation suffices alone; in concert they close
the cross-turn continuity loop.

## 2. Result IR object

The Result IR is a single JSON object with exactly three top-level members:

```
{
  "files":          [ FileEntry, ... ],      // non-empty
  "reconciliation": [ Reconciliation, ... ], // non-empty
  "open_defects":   [ Defect, ... ]          // possibly empty
}
```

**FileEntry**:

```
{ "filename": "<name>.py",
  "satisfies": ["R<n>", ...],
  "evidence": Evidence }
```

**Reconciliation**:

```
{ "requirement": "R<n>",
  "status": "satisfied" | "partial" | "open",
  "evidence": Evidence }
```

**Defect**:

```
{ "id": "D<n>",
  "description": "<defect statement>",
  "evidence": Evidence }
```

**Evidence**:

```
{ "path": "<workspace-relative artifact path>",
  "section": "<verbatim section marker inside the artifact>",   // optional
  "observed": "<verbatim quote from the artifact>"              // optional, REQUIRED for status/defect claims
}
```

Clauses:

**RS-01 —** The Result IR SHALL be emitted by the EXECUTE operation as the final fenced
```json block of the execution body, in the shape of Section 2.

**RS-02 —** Requirement IDs (`R<n>`) SHALL be derived mechanically by the controller from
the confirmed Prompt Pseudocode body: every body line whose first token is a commitment
verb is promoted to one requirement, numbered in order of appearance. The numbered list
SHALL be supplied to the executor in the execution projection.

**RS-03 —** The reconciliation array SHALL contain every requirement ID derived per RS-02
exactly once, with status `satisfied`, `partial`, or `open`.

**RS-04 —** Every Evidence object SHALL cite a workspace-relative path that resolves to an
existing file inside the workspace boundary. Paths that escape the workspace SHALL be
rejected.

**RS-05 —** Every `section` citation SHALL appear verbatim inside the cited artifact.

**RS-06 —** Every `observed` citation SHALL be a verbatim substring of the cited artifact.
Paraphrase, summary, and invention are violations.

**RS-07 —** Every `partial` or `open` status and every open defect SHALL carry an
`observed` citation (the failure is a fact only when quotable).

**RS-08 —** The controller SHALL validate the Result IR mechanically before publishing:
schema shape (RS-01), coverage and uniqueness (RS-03), path resolution (RS-04), section
and observation verbatim checks (RS-05/06), and status evidence requirements (RS-07).
Validation failures SHALL trigger exactly one operator-correction retry; persistent
failures SHALL be published as workspace events and scored as model errors, never
silently masked.

**RS-09 —** On continuation epochs the controller SHALL inject the prior epoch's
validated Result IR into the execution projection alongside the byte-exact prior
deliverable, and SHALL treat the reconciliation statuses and open defects as
authoritative continuation state across process restarts (restore included).

**RS-10 —** This standard SHALL be feature-gated (`PDLT_RESULT_IR=1`) until ratified into
the normative contract store; the recorded and qualified paths SHALL remain
byte-identical with the gate off.

## 3. Relationship to native artifacts

Per ADR-0005's preservation clause, the Result IR never replaces the native deliverable:
the native artifact remains the execution output; the IR is appended to it (RS-01) and
chained beside it (RS-09). Where a required native artifact cannot be represented in the
IR, the IR SHALL cite it; the native bytes remain the compile-time truth.
