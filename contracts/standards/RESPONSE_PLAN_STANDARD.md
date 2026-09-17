# Response Plan Standard

Normative scope: Response Plan Pseudocode coverage, abstraction, neutrality, and revision.

**PLAN-01 — Coverage before minimization.** For each material action or deliverable in the confirmed Prompt Pseudocode, the Response Plan MUST represent it with a high-level operation or cover it unambiguously with a broader operation.

**PLAN-02 — Minimum sufficient procedure.** The Response Plan MUST expose only enough procedure for the user to reject a materially undesirable response approach.

**PLAN-03 — Neutrality.** The Response Plan MUST remain neutral and high-level.

**PLAN-04 — No answer leakage.** The Response Plan MUST NOT answer the request, anticipate findings, choose winners, invent hypotheses, lock arguments, preselect substantive conclusions, or otherwise perform the requested task.

**PLAN-05 — No unnecessary implementation commitment.** The Response Plan MUST NOT choose unrequired sources or over-specify evidence, examples, calculations, sections, or low-level reasoning.

**PLAN-06 — No substantive research.** Response Plan generation MUST NOT research the substantive task.

**PLAN-07 — Revision semantics.** A Plan revision MUST keep the confirmed Prompt fixed, apply only changed `TASK-02` semantics, and preserve `PLAN-01` through `PLAN-03`.

**PLAN-08 — Carried approach constraints.** When ordered `TASK-02` projections are supplied to a Plan operation, the Response Plan MUST incorporate their operative approach constraints while remaining consistent with the confirmed Prompt and the other Plan requirements.

**PLAN-09 — Message-act response coverage.** When Prompt Pseudocode represents a user message-act with no requested material action or deliverable (`SEM-05`), the Response Plan MUST represent the agent's responsive action to that act.

**PLAN-10 — Negative constraint operationalization by omission.** When Prompt Pseudocode specifies negative constraints, exclusions, or unhandled conditions (e.g. "do not do X", "let unhandled exceptions propagate"), the Response Plan MUST operationalize them as structural omission rather than defensive assertions, catch-all wrappers, or redundant re-raises. In programming deliverables, native platform propagation and runtime defaults MUST be relied upon without generating active procedural steps for unrequested conditions.

