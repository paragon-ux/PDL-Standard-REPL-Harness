# Authority Standard

Normative scope: ownership of correctness, task authority, orchestration, and calibration authority.

**AUTH-01 — Sole normative authority.** Standard Contracts are the only normative source for model-independent protocol and runtime correctness.

**AUTH-02 — Downstream boundary.** A controller, Execution Contract, Verification Contract, context compiler, worker prompt, calibration item, example, checklist, or architecture note MAY decide where, when, or how to apply or check a requirement, but MUST NOT independently decide or redefine what constitutes correct protocol behavior.

**AUTH-03 — Confirmed task authority.** After confirmation, the current confirmed Prompt Pseudocode defines authoritative task semantics and the current confirmed Response Plan Pseudocode defines the approved high-level approach, subject to higher-priority safety, privacy, platform, permission, and tool constraints.

**AUTH-04 — Source-input role.** Original conversational wording and source inputs remain provenance and task data. They MUST NOT silently override conflicting confirmed task semantics after confirmation.

**AUTH-05 — Mechanical/semantic separation.** The controller owns mechanically decidable lifecycle and artifact facts and MUST NOT independently determine the meaning of natural-language task or review content.

**AUTH-06 — Semantic-worker boundary.** A semantic worker may determine meaning-dependent Prompt content, Plan content, review intent, and substantive execution content. It MUST NOT be authoritative for host-owned identity, currentness, confirmation state, persistence, or replay bookkeeping.

**AUTH-07 — Calibration non-authority.** Calibration material MAY illustrate Standard requirements but MUST NOT define correctness. Removing a calibration item MUST NOT change what constitutes correct behavior.
