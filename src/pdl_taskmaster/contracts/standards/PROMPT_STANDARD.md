# Prompt Standard

Normative scope: Prompt Pseudocode content and revision.

**PROMPT-01 — Semantic fidelity.** Prompt Pseudocode MUST represent all and only operative `TASK-01` semantics that remain applicable to the requested work after the confirmation protocol is complete.

**PROMPT-02 — No substantive solution.** Prompt Pseudocode MUST NOT solve the task, research task facts, inspect task-specific resources, plan the response, or include substantive task findings.

**PROMPT-03 — No invented requirements.** Prompt Pseudocode MUST NOT invent missing requirements or silently improve the user's request.

**PROMPT-04 — Unspecified details.** If a detail is unspecified, Prompt Pseudocode MUST represent the request as currently understood. Prompt generation MUST NOT be replaced with clarification unless a higher-priority requirement makes the missing input genuinely blocking.

**PROMPT-05 — Revision semantics.** A Prompt revision MUST apply the user's changed `TASK-01` semantics and preserve every current `TASK-01` requirement not changed by the user.
