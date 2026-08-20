# Context Standard

Normative scope: assembly and isolation of model-operation context.

**CONTEXT-01 — Positive inclusion.** Each model-operation context MUST be assembled from a positive inclusion set rather than from the full conversation or repository followed by subtraction.

**CONTEXT-02 — Applicable normative clauses only.** A semantic worker MUST receive only the Standard clauses selected as applicable to its requested operation, plus higher-priority constraints.

**CONTEXT-03 — Authoritative task inputs only.** A semantic worker MUST receive only task/artifact inputs authorized for its requested operation.

**CONTEXT-04 — Rejected-context exclusion.** Rejected or obsolete artifact bodies MUST NOT enter a later semantic operation unless an explicitly authorized diagnostic operation requires them.

**CONTEXT-05 — No implicit repository authority.** Repository-wide discovery MUST NOT become an implicit instruction source.

**CONTEXT-06 — Confirmed-artifact preservation.** When confirmed Prompt or Plan content is supplied to a later operation, the authoritative artifact content MUST be preserved exactly unless that operation is the authorized revision of that artifact.
