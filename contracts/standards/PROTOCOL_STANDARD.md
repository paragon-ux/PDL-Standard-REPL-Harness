# Protocol Standard

Normative scope: activation, lifecycle ordering, substantive-work gating, and instance closure.

**PROTO-01 — Activation.** The protocol applies when the skill is explicitly invoked or when the user asks to confirm request meaning and response approach before substantive work. A request that only discusses or modifies the protocol without asking to apply it does not activate a task instance.

**PROTO-02 — Ordered confirmation.** The current Prompt Pseudocode MUST be confirmed before Response Plan Pseudocode confirmation begins, and the current Response Plan Pseudocode MUST be confirmed before substantive execution begins.

**PROTO-03 — Pre-execution gate.** Before both current artifacts are confirmed, substantive task work MUST NOT be performed, including task research, task-specific resource inspection, calculations, requested comparisons, requested findings or recommendations, final-deliverable drafting, or substantive task-tool use.

**PROTO-04 — Review-stage discussion.** Protocol/process/PDL-notation discussion MAY be answered during review. Task-domain substantive discussion before execution MUST be deferred.

**PROTO-05 — Fresh instance.** A clearly independent new substantive task starts a fresh protocol instance. Confirmation or artifact state from another instance MUST NOT be carried into it.

**PROTO-06 — Cancellation.** Cancellation closes the active protocol instance without substantive execution.

**PROTO-07 — Completion closure.** Successful completion closes the active protocol instance.
