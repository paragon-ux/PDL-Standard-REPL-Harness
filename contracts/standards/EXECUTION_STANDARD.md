# Execution Standard

Normative scope: execution-time missing input and external-action behavior after the protocol execution gate has been satisfied.

**EXEC-01 — Missing non-semantic input.** If required non-semantic execution input is missing, request only that input, wait for it, and do not create a third confirmation stage.

**EXEC-02 — Semantic change while waiting.** If the user changes `TASK-01` while execution is waiting for input, the protocol MUST return to Prompt revision/review before substantive execution continues.

**EXEC-03 — Cancellation and external action.** If the user cancels before the next host-observable execution action, remaining reversible work MUST stop. The system MUST NOT claim to reverse an already-completed or in-flight external action.
