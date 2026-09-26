# Review Standard

Normative scope: semantic classification and precedence of review messages.

**REVIEW-01 — Pure confirmation.** `PURE_CONFIRMATION` means the user accepts the current review subject and adds no `TASK-01` change, `TASK-02` change, or revision request.

**REVIEW-02 — Task change.** `TASK_CHANGE` means the user changes `TASK-01`.

**REVIEW-03 — Approach change.** `APPROACH_CHANGE` means the user changes only `TASK-02`.

**REVIEW-04 — Cancellation.** `CANCEL` means the user asks to stop the current protocol instance without execution.

**REVIEW-05 — New task.** `NEW_TASK` means the user explicitly abandons or sets aside the current task and begins clearly independent substantive work.

**REVIEW-06 — Protocol discussion.** `PROTOCOL_DISCUSSION` means the user asks only about the protocol, review stage, or PDL notation.

**REVIEW-07 — Substantive discussion.** `SUBSTANTIVE_DISCUSSION` means the user requests task-domain facts, analysis, likely findings, comparisons, recommendations, or other substantive work before execution.

**REVIEW-08 — Execution input.** `SUPPLY_EXECUTION_INPUT` means the user supplies requested non-semantic execution data without changing `TASK-01` or `TASK-02`.

**REVIEW-09 — Unresolved intent.** If operative intent is materially uncertain, interpretation MUST be `UNRESOLVED`; the protocol MUST NOT progress on the basis of that message.

**REVIEW-10 — Change precedence.** If confirmation and a change coexist, the change MUST be applied and the message MUST NOT progress by confirmation in the same turn.

**REVIEW-11 — Mixed task/approach change.** If `TASK-01` and `TASK-02` changes coexist, the task change MUST govern the immediate revision path and the approach instruction MUST remain available for the later Plan operation.

**REVIEW-12 — Cancel plus new task.** If cancellation and a clearly independent new task coexist, the old instance MUST close and the new task MUST start as a fresh instance.

**REVIEW-13 — Change plus substantive side question.** If a semantic change and a substantive side question coexist before execution, the semantic change MUST be applied and the substantive answer MUST be deferred.

**REVIEW-14 — No silence confirmation.** Silence MUST NOT be interpreted as confirmation.
