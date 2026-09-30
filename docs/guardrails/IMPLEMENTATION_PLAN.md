# Implementation Plan: Harness Anti-Overfitting & Guardrail Enforcement

## 1. Objectives & Scope

This implementation plan operationalizes the **Anti-Overfitting and Benchmark Integrity Guardrail (GUARD-01 through GUARD-05)** across the `pdl-taskmaster` codebase. It establishes automated, continuous enforcement to guarantee that the harness remains an impartial protocol governor and never degrades into a benchmark-gaming solver.

---

## 2. Phased Roadmap

### Phase 1: Automated Harness Purity Linter (`tests/test_harness_anti_overfitting.py`)
- **Action**: Create an automated test suite that parses the AST and string literals of all files under `src/pdl_taskmaster/`.
- **Invariants Checked**:
  1. `session_engine.py`: Assert that `_draft_plan` does not inject synthetic carried approach strings when `carried_raw` is empty.
  2. `problem_class.py`: Assert that `_COMBINATORIAL_PATTERNS` does not contain conversational/riddle keywords (`sisters`, `brothers`, `riddle`, `family relationship`).
  3. `activation_route.py`: Assert that regex patterns and refusal responses do not hardcode single benchmark prompt tokens (`frostbitedb`, `nobel prize`).
  4. `output_verifier.py`: Assert that `detect_domain` does not match the token `"triples"` without partition/sum qualifiers.
  5. `CONTRACT_MANIFEST.json`: Assert that all contract and standard SHA-256 hashes match files on disk with zero divergence.
- **Success Criteria**: `pytest tests/test_harness_anti_overfitting.py` passes 100% green.

### Phase 2: Decoupling Plan Soundness from Compulsory Code Execution
- **Action**: Refactor `src/pdl_taskmaster/verification/plan_soundness.py`.
- **Changes**:
  1. Retain universal anti-deferral gates: reject `TBD`, `undecided`, `deferred to execution`, `no-backtrack greedy pass presented as decisive`.
  2. Modify the code execution commitment check (`_CODE_EXECUTION_COMMITMENT_PATTERNS`):
     - For tasks where the prompt requests code implementation or combinatorial witness search, require algorithmic commitment.
     - For tasks where the prompt requests analytical deduction, explanation, or closed-form math, accept procedural analytical verbs (`ANALYZE`, `DEDUCE`, `DERIVE`, `COMPUTE`, `PROVE`).
- **Success Criteria**: Response plans for symbolic deduction (e.g. `ANALYZE sibling relations`, `DEDUCE total sisters`) pass `validate_plan_soundness` without requiring `python` or `backtracking`.

### Phase 3: Symbolic Reasoning Verification Battery
- **Action**: Add a new dedicated test suite `tests/test_symbolic_reasoning.py`.
- **Test Cases**:
  1. *Alice Siblings Deduction*: Alice has $N$ brothers and $M$ sisters. Verify the model correctly deduces $M+1$ sisters for each brother without fabricating $N=3, M=4$ or writing a backtracking script.
  2. *Parity Derivation*: Prove that the product of an even integer and an odd integer is even. Verify result IR accepts pure mathematical prose (`files: []`, `execution://body`).
  3. *Closed-Form Algebra*: Simplify $(x+1)^2 - (x-1)^2$. Verify no numerical dummy values are invented.
- **Success Criteria**: All symbolic tests pass without invoking Python sandbox execution or fabricating witness JSON.

### Phase 4: Integration into Baseline Verifier (`pdlt verify`)
- **Action**: Update `src/pdl_taskmaster/verify/verify_repl_baseline.py` to run the Anti-Overfitting purity checks as part of the mandatory baseline gate.
- **Success Criteria**: `pdlt verify` fails if any engineer attempts to re-introduce a benchmark-specific token or synthetic approach injection.

---

## 3. Maintenance & Review Governance

1. **ADR Alignment Requirement**: Any future ADR proposing changes to prompt templates, System 1 recipes, or verifiers must explicitly cite compliance with `GUARD-01` through `GUARD-05`.
2. **Zero-Tolerance for Goodhart Leaks**: PRs containing prompt-targeted regexes or solver injections must be rejected immediately during code review.
