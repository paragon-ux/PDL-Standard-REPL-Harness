# ADR-0018: Elimination of Regex Heuristics in Substantive Verification & Reconciliation Semantic Integrity

- **Status:** ACCEPTED
- **Date:** 2026-09-29
- **Related Decisions:** [ADR-0010 Pydantic Wire Enforcement](0010-pydantic-wire-enforcement.md), [ADR-0013 Substantive Correctness Verification](0013-substantive-correctness-verification.md), [ADR-0015 Model-Synthesized Verification](0015-model-synthesized-verification-and-confinement-boundaries.md), [ADR-0016 Pydantic SSOT Deliverable Enforcement](0016-pydantic-ssot-wire-and-deliverable-boundary-enforcement.md), [ADR-0017 Dual-Plane Runtime Realignment](0017-dual-plane-runtime-realignment-and-mrv-solver-governance.md)
- **Evidence:** `session-20260929-063836` (`REG-010`: regex synonym dropout, `nodes_explored: 0` negative witness acceptance, and contradictory reconciliation of existential requirement R2).

---

## 1. Context & Problem Statement

In `session-20260929-063836`, during evaluated benchmark execution of the 45-integer Schur Triples problem ($N=15$), the model emitted bare Python solver code without markdown code fences or explicit `### solver.py` delivery headers. While the emitted backtracking solver was algorithmically correct and solved the instance in $<50\text{ms}$, several interconnected architectural vulnerabilities compromised the verification and Result IR repair boundary:

1. **The Heuristic Regex Whack-a-Mole (Anti-Pattern):**
   In early development, `OutputVerifier.detect_domain` utilized an ad-hoc regular expression (`re.search(r"(?i)\b(?:schur\s+triples?|partitioned?\b[^.\n]*\btriples?|sum\s+triples?)\b", text)`) to guess which domain checker to invoke. When the model authored prompt pseudocode using the valid natural-language synonym *"divided into 15 disjoint triples"*, the regex silently failed. As a consequence, domain routing dropped from `PartitionSumTriplesChecker` to `FallbackChecker`.
2. **Ungrounded Negative Witness Acceptance:**
   Because `NegativeWitness.nodes_explored` was typed as a loose `int` rather than `PositiveInt` ($> 0$), and `search_exhausted` was typed as `bool` rather than `Literal[True]`, `FallbackChecker` accepted a fabricated negative witness claiming `search_exhausted: True` with `nodes_explored: 0`. Exploring zero nodes cannot certify the non-existence of combinatorial structures.
3. **Contradictory Result IR Reconciliation:**
   During Result IR repair (`EMIT_RESULT_IR`), the model claimed that all derived requirements (R1, R2, R3) were `"status": "satisfied"` by citing `"observed": "polarity\":\"negative\""`. Requirement R2 explicitly demanded: *"GENERATE one concrete example of 15 triples satisfying the condition."* Claiming that a generation requirement is satisfied via a negative witness (non-existence) is a direct logical contradiction that escaped structural validation.
4. **Sandbox Code Extraction Blind Spot:**
   `session_engine.py` parsed executable blocks using strict markdown fences (`re.findall(r"```(?:python|py)?\s*\n(.*?)```", final_body)`). When the model delivered bare Python code, zero blocks were extracted. Furthermore, when `print(witness)` printed a Python dictionary literal containing single quotes (`{'polarity': ...}`), `json.loads` threw a decode error while `ast.literal_eval` only checked `isinstance(p_obj, list)`, ignoring dictionary objects and failing to ground the verified solution.

---

## 2. Decision Drivers

- **Pydantic as Single Source of Truth (SSOT):** Verification dispatch, witness schemas, and reconciliation integrity must be governed by typed Pydantic models and canonical enums—never by ungrounded regex keyword matching.
- **Fail-Closed Mechanical Guarantees:** Contradictory reconciliation (e.g. claiming existential generation is satisfied by a non-existence certificate) must fail validation before execution completes.
- **Strict Witness Typing:** Proof of non-existence requires exhaustive search certificates with strictly positive exploration bounds (`nodes_explored > 0`, `search_exhausted: True`).
- **Resilient Execution Sandbox Ingestion:** Code extraction and sandbox witness parsing must accept both markdown-fenced code blocks and bare Python source, robustly parsing single-quoted Python dictionary outputs via `ast.literal_eval`.

---

## 3. Decision

The harness architecture SHALL replace regex domain heuristics and loose dictionary inspection with strict Pydantic models across the verification plane:

### 3.1 Canonical `ProblemDomain` Enum & Sovereign Dispatch
- Define `ProblemDomain(str, Enum)` in `pdl_taskmaster.verification.checkers.base`:
  - `PARTITION_SUM_TRIPLES = "partition_sum_triples"`
  - `EXACT_COVER = "exact_cover"`
  - `SUBSET_SUM = "subset_sum"`
  - `GENERAL = "general"`
- `SessionEngine` explicitly sets `self._problem_domain` during upfront problem classification (`_draft_initial_prompt`) and records it in workspace events (`PROBLEM_CLASS_CLASSIFIED`).
- `OutputVerifier.check()` accepts `domain: ProblemDomain | str | None` and dispatches directly via dictionary lookup.
- Regex pattern matching is eliminated from `OutputVerifier.detect_domain`.

### 3.2 Strict Pydantic Witness Models (`wire_payloads.py`)
- `NegativeWitness` enforces strict literal exhaustion and strictly positive state counts:
  ```python
  class NegativeWitness(BaseModel):
      model_config = ConfigDict(extra="forbid")
      polarity: Literal["negative"] = "negative"
      evidence: Evidence = Field(default_factory=lambda: Evidence(path="execution://witness"))
      search_exhausted: Literal[True] = True
      nodes_explored: PositiveInt  # Must be strictly > 0
      method: str = Field(min_length=3)
  ```
- `WitnessPayload` is configured as a discriminated union on `polarity`:
  ```python
  WitnessPayload = Annotated[
      Union[PositiveWitness, NegativeWitness],
      Field(discriminator="polarity"),
  ]
  ```
- Substantive domain checkers (`PartitionSumTriplesChecker`, `FallbackChecker`) validate candidate witnesses via `model_validate()` at their entry boundary.

### 3.3 Reconciliation Semantic Integrity Invariant (`result_ir.py`)
- `validate_result_ir` incorporates Phase 3 semantic integrity validation:
  - If `witness.polarity == "negative"`, the validator inspects all reconciliation items marked `"satisfied"`.
  - If a requirement contains existential or generative instructions (`GENERATE`, `PROVIDE`, `CONSTRUCT`, `FIND`, `EXAMPLE`), claiming `"status": "satisfied"` on a negative witness is rejected as a semantic contradiction (`contradictory_reconciliation`).

### 3.4 Python AST & Bare Execution Recovery (`session_engine.py`)
- `_parse_sandbox_witness` supports dictionary evaluation from `ast.literal_eval`, correctly ingesting `print(witness)` emissions from Python scripts.
- Sandbox extraction detects bare Python code without fences when import/definition/print primitives are present, ensuring candidate scripts are executed in `ExecutionSandbox`.

### 3.5 Absolute Prohibition of Deliverable Text Scraping (GUARD-05 / Anti-Gaming Amendment)
- Substantive domain checkers SHALL NEVER employ regular expressions or string parsers to scrape deliverables (e.g. searching raw markdown text for triple lists) in order to fabricate or recover missing witnesses.
- If the model's Result IR or sandbox execution output fails to produce a well-formed structured witness conforming to Pydantic schemas, verification MUST fail-closed (`VerificationVerdict(valid=False)`).
- Synthetic witness generation from deliverable prose is strictly prohibited.

---

## 4. Consequences & Impact

- **Zero Regex Vulnerability & Deliverable Integrity:** Domain routing, witness parsing, and verification constraints are decoupled from natural language prompt phrasings, eliminating both synonym bypass bugs and artificial witness synthesis via deliverable scraping.
- **Impossibility of False Green via Empty Claims:** Models cannot bypass verification by claiming non-existence with 0 nodes explored, nor claim satisfaction of generation requirements on negative search results.
- **Alignment with ADR-0016:** Extends Pydantic-as-SSOT from wire payloads to the substantive verification plane.

