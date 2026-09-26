# RESULT_STANDARD: Result Pseudocode Decomposition with Evidence Citations

> Normative standard for the EXECUTE operation's structured Result IR.
> Ratified as TRD-0003 (prototype, feature-gated per RS-10); ADR-0009 is the
> governing decision. The controller SHALL load this standard at the
> execution stage and render its instruction block into the execution
> projection when the feature gate is active.

**RS-01 —** The EXECUTE operation SHALL emit a Result IR object as the final fenced ```json block of the execution body, shaped exactly as: {"files": [{"filename": str, "satisfies": [str...], "evidence": {"path": str, "section": str?, "observed": str?}}], "reconciliation": [{"requirement": "R<n>", "status": "satisfied|partial|open", "evidence": {...}}], "open_defects": [{"id": "D<n>", "description": str, "evidence": {...}}]}.

**RS-02 —** Requirement IDs R1..Rn SHALL be derived mechanically by the controller from the confirmed Prompt Pseudocode body: every line whose first token is a commitment verb is one requirement, numbered in order; the numbered list SHALL be rendered into the execution projection.

**RS-03 —** The reconciliation array SHALL contain every derived requirement ID exactly once, with status satisfied, partial, or open.

**RS-04 —** Every evidence path SHALL resolve to an existing file inside the workspace boundary, OR SHALL be the reserved self-reference `execution://body` resolved by the controller to the current execution body (the just-produced deliverable, which is not yet on disk at validation time). Escaping paths are invalid.

**RS-05 —** Every cited section marker SHALL appear verbatim in the cited artifact.

**RS-06 —** Every cited observation SHALL be a verbatim substring of the cited artifact; paraphrase and invention are violations.

**RS-07 —** Every partial or open status and every open defect SHALL carry a verbatim observed citation.

**RS-08 —** The controller SHALL validate the Result IR mechanically (shape, coverage, uniqueness, resolution, verbatim checks) before publishing; exactly one operator-correction retry is permitted on failure; persistent failures SHALL be published as workspace events and scored as model errors.

**RS-09 —** On continuation epochs the controller SHALL inject the prior validated Result IR beside the byte-exact prior deliverable, and reconciliation state SHALL survive process restarts.

**RS-10 —** This standard SHALL be feature-gated (PDLT_RESULT_IR=1) until ratified into the recorded qualification tiers; the recorded and qualified paths SHALL remain byte-identical with the gate off.

<!-- RESULT-IR:INSTRUCTIONS (controller renders this block verbatim into the
     execution projection, then appends the numbered requirement list) -->
The response MUST end with a fenced ```json block containing the Result IR object, exactly this shape:
{"files": [{"filename": "<name>.py", "satisfies": ["R<n>"], "evidence": {"path": "<workspace-relative path>", "section": "<verbatim section marker, optional>"}}], "reconciliation": [{"requirement": "R<n>", "status": "satisfied|partial|open", "evidence": {"path": "...", "section": "...", "observed": "<verbatim quote from the cited artifact>"}}], "open_defects": [{"id": "D<n>", "description": "<defect>", "evidence": {"path": "...", "observed": "<verbatim quote>"}}]}
Evidence rules: the path "execution://body" refers to THIS response's own deliverable text (use it for code and claims that exist only in this response); any other path MUST be one of the AVAILABLE EVIDENCE PATHS listed below; every "observed" string MUST be copied verbatim from the cited artifact; every requirement ID MUST appear in "reconciliation" exactly once; do not invent paths, sections, quotes, or requirement IDs; the host mechanically validates every citation and rejects fabrication.
AVAILABLE EVIDENCE PATHS: {evidence_paths}
<!-- /RESULT-IR:INSTRUCTIONS -->
