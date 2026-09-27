# Definition of Done: Substantive Correctness & Verification Architecture

- **Status:** DRAFT (v2 — supersedes v1; reflects real paths and the
  merged Claude/Gemini roadmap)
- **Target Version:** v2.4.2
- **Related Plan:** [substantive-correctness-verification.md](../implementation-plans/substantive-correctness-verification.md)
- **Related Decision:** [ADR-0013](../../adr/0013-substantive-correctness-verification.md)

---

## 1. Cardinal Invariants

- [ ] **No plan reaches execution ungrounded:** for `requires_verified_execution`
  requests, no Response Plan enters the `.../stages/50_execution/` stage
  while containing deferral language or an undisclosed incomplete
  algorithm (P0).
- [ ] **No answer is self-graded:** the output verifier is deterministic,
  harness-owned code — never a model call asked to grade sys2's own or a
  peer's work (P2).
- [ ] **No unwitnessed final answers:** `result_ir.witness` is populated,
  in the correct polarity shape, for every `requires_verified_execution`
  result before it is shown as final (P1).
- [ ] **No ungrounded introspection:** a "show your work" turn either
  cites the projected witness or states plainly that no trace exists —
  never freshly-generated content standing in for either (P3).

## 2. P0 — Plan Soundness

- [ ] Rejects the literal deferred-plan text from `session2-v-2-4-0.txt`.
- [ ] Rejects an undisclosed single-pass/no-backtrack greedy scan proposed
  as decisive.
- [ ] Accepts a plan that commits to real code execution for the search.
- [ ] After `MAX_PLAN_REDRAFTS` rejections, surfaces the specific failure
  to the user rather than looping silently.

## 3. P1 — Witness Schema

- [ ] `ResultIRPayload.witness` accepts both `PositiveWitness` (with
  solution `data`) and `NegativeWitness` (with `search_exhausted`,
  `nodes_explored`, `method`).
- [ ] Re-running the `session-20260927-052351` turn-1 scenario against the
  new schema produces a non-empty, correctly-typed `witness` field —
  the original recorded payload (`witness` absent entirely) is the
  before-state regression check.

## 4. P2 — Verification & Retry

- [ ] Rejects a positive witness where any input element is duplicated,
  any input element is missing, or any triple fails `a + b == c`
  (partition-sum-triples checker).
- [ ] Rejects a negative witness where `search_exhausted` is `false` or
  absent.
- [ ] Verifier failures are asserted, via a mocked sys2 client, to route
  through the same bounded retry mechanism exercised by
  `test_wire_repairs.py` — not a separate, unbounded loop.
- [ ] After the retry budget is exhausted, the harness returns an explicit
  "unverified, here's why" result rather than the last failed candidate.

## 5. P3 — Grounded Introspection

- [ ] An introspection request for a turn with a populated witness returns
  content drawn from `REQUIRED_TASK_INPUTS`, not freshly reasoned content.
- [ ] An introspection request for a turn with **no** witness returns an
  explicit "no trace exists" statement — this is a direct regression test
  against the fabricated `{1,2,3,4,5,6}` / Schur's-theorem justification
  observed in `session9-v-2-4-0.txt`.
- [ ] The regression assertion checks for the *absence* of invented
  specifics (no numbers, sets, or derivations not present in the actual
  witness) rather than only checking for the presence of a disclaimer —
  a response could contain both a disclaimer and fabricated content.

## 6. P4 — Fixtures & Fallback

- [ ] `session9-v-2-4-0.txt` and `session2-v-2-4-0.txt` are both captured
  as permanent regression fixtures (mocked sys2 responses reproducing
  each observed failure in sequence).
- [ ] The 45-integer / N=15 adversarial instance is registered as a
  standing manual-QAT case.
- [ ] A `requires_verified_execution` request with no registered domain
  checker returns a result labeled `"provisional"`, not silently passed
  through as verified.

## 7. Test Suite & Regression Bar

- [ ] Zero regressions against the existing suite (27+ tests as of the
  last recorded run) plus all fixtures above.
- [ ] The independently-verified correct answers already on record — the
  optimal 4-cut palindrome partition (`session8-v-2-4-0.txt`) and the
  valid Schur-triples partition for the 45-number instance — are used as
  the *positive* regression cases: the new pipeline must still reach
  these same correct answers, now with a populated, verifiable witness
  attached, not a different (possibly worse) answer.

## 8. Human QAT Sign-Off

- [ ] User re-runs `session9-v-2-4-0.txt`'s scenario end-to-end and
  confirms: the plan commits to real search before execution, the final
  answer carries a witness, and the "show your work" follow-up either
  reproduces the real derivation or explicitly states none was retained
  — never a fabricated one.
- [ ] User confirms ADR numbering (`0013`) does not collide with anything
  merged between v1 and v2 of this document set.
- [ ] No git commit or merge until the user explicitly confirms QAT
  passed.
