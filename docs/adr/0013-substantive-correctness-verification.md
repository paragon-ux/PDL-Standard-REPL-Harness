# ADR-0013: Verified Execution and Bidirectional Witness Retention for Substantive Correctness

- **Status:** ACCEPTED (shipped in v2.5.0)
- **Date:** 2026-09-27 (v2 — supersedes the v1 draft from earlier the same day)
- **Related:** [ADR-0014 dual-plane boundary and wire conformance](0014-dual-plane-boundary-and-wire-conformance.md), [substantive-correctness-verification.md](../pdlt-docs/implementation-plans/substantive-correctness-verification.md)
- **Evidence:** `session8-v-2-4-0.txt` (correct, DP-verified palindrome partition), `session9-v-2-4-0.txt` (correct bare "YES" on the Schur-triples instance, followed by a fabricated justification), the on-disk `result_ir` for `session-20260927-052351` turn 1, and a second-reviewer (Gemini) analysis of the same evidence.

> **One correction from v1:** this ADR now lives at `docs/adr/`, not
> nested under `docs/pdlt-docs/adr/` as originally drafted — the real
> commit log shows ADR-0014 at the repo-root `docs/adr/`, and this
> supersedes the misplaced v1 copy. Confirm `0013` is still unclaimed in
> your sequence before merging; renumber to the next free slot if not.

---

## Context

ADR-0012 (sys1/sys2 split) and ADR-0014 (dual-plane boundary, Pydantic
wire conformance) fix how the harness routes dialogue and validates
message *shape*. Neither addresses whether a substantive answer is
*true*.

Two independent lines of evidence converged on the same gap:

1. **Behavioral evidence (session8/session9 transcripts).** Both final
   answers were independently verified as correct — a DP re-solve of the
   palindrome partition confirmed 4 cuts is optimal, and the Schur-triples
   instance does have a valid 15-triple partition. But when asked to
   justify the Schur-triples "YES," the model produced a fully fabricated
   derivation using an invented 6-element set and an irrelevant citation
   of Schur's coloring theorem, closing with a false claim that all
   requirements had been addressed.
2. **On-disk evidence (`result_ir` for that turn).** The raw execution
   payload confirms *why*: `body: "YES"` with `result_ir.files` and
   `result_ir.reconciliation` both pointing only at `evidence.path:
   "execution://body"` — no candidate triples, no search trace, nothing
   for a later turn to draw on. The confabulation wasn't a one-off lapse;
   given an empty ledger, it was the only thing turn 2 *could* produce.

A second review pass (Gemini, working from the on-disk payload) proposed
mandatory witness retention plus a mechanical post-hoc verifier. That
closes the retrieval gap but leaves two things unaddressed: nothing
constrains *how* sys2 arrives at an answer before execution runs (the
first observed failure, in `session2-v-2-4-0.txt`, was a plan that
committed to a structurally-incomplete no-backtrack greedy scan — a
post-hoc verifier would have caught the wrong answer, but only after
burning an attempt on an approach that could not have succeeded), and the
witness schema as proposed only has shape for a positive ("YES") answer,
leaving a "NO" backed by real exhaustive search indistinguishable from a
"NO" backed by one failed heuristic pass.

## Decision

For any request classified `requires_verified_execution` (asks whether a
combinatorial structure exists, or for an exact/optimal solution with a
checkable witness), the harness enforces, in this order:

**P0 — Plan-time execution commitment.** Before the stage pipeline
transitions into execution (the `.../stages/50_execution/` stage
observed in the run tree), the Response Plan is checked for a concrete
commitment to real code execution for the search itself. A plan that
proposes freeform reasoning, a single undisclosed greedy pass, or defers
the method to execution time is rejected and returned to sys2 with the
specific violation, bounded to a fixed number of redrafts.

**P1 — Deterministic, OS-native sandboxed execution plane (`ExecutionSandbox`).**
Untrusted code and search scripts committed to under P0 SHALL run inside a local, OS-native sandbox (`src/pdl_taskmaster/verification/sandbox.py`) before results reach the verifier:
- **Zero-Dependency Native Process Isolation:**
  - **Windows:** Windows Job Objects (bound via standard library `ctypes` calling `kernel32.dll`), enforcing `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `JOB_OBJECT_LIMIT_JOB_MEMORY` (256MB), and idle priority. All child processes and runaway threads are killed automatically by the Windows kernel on close. Process startup overhead is $\le 1\text{ms}$ (total execution turnaround $<20\text{ms}$).
  - **POSIX (Linux/macOS):** `resource.setrlimit` (`RLIMIT_AS` memory ceiling, `RLIMIT_CPU` time ceiling) and process isolation.
- **Strict Confinement Policy:**
  - **Network:** Zero outbound network access (`python -I -s`, sockets blocked).
  - **Timeout:** Hard 5.0-second wall-clock ceiling per execution attempt.
  - **Memory:** Strict 256MB RAM ceiling (OS kernel terminates runaway allocations).
  - **Filesystem:** File writes strictly restricted to an ephemeral scratchpad directory discarded immediately after execution.

**P2 — Bidirectional witness retention.** `ResultIRPayload`
(`runtime/wire_payloads.py`) gains a `witness` field, populated for both
polarities:
- positive (`YES`): the actual solution structure (e.g. the 15 triples).
- negative (`NO`): a certificate — `search_exhausted: bool`,
  `nodes_explored: int`, `method: str` — distinguishing a proven
  non-existence from a heuristic that merely failed once.

This extends the existing `files[].evidence` / `reconciliation[].evidence`
convention already established under ADR-0014 rather than introducing a
parallel structure.

**P3 — Mechanical, bounded verification.** A deterministic checker (plain
code, never a model call) validates the witness — arithmetic/coverage for
a positive claim, `search_exhausted == true` for a negative one — before
the execution gate closes. Failures route through the same bounded
repair-attempt mechanism already exercised by `test_wire_repairs.py`
rather than a new, separately-unbounded loop. Exhausting the budget
produces an explicit "unverified after N attempts, last failure: X"
result, never a silent fallback to an unverified answer.

**P4 — Grounded-only introspection.** The Cumulative Turn Ledger
(`runtime/session_engine.py`) projects the stored witness into
`REQUIRED_TASK_INPUTS` for any later turn asking to see the reasoning.
The instruction for that turn constrains sys2 to cite only the projected
data and to say plainly that no trace exists when the field is empty —
this is a stated constraint on the turn, not an assumption that
witness availability alone prevents embellishment around it.

**P5 — Regression coverage.** `session9-v-2-4-0.txt` (not the earlier,
less specific session2 transcript) becomes the primary anti-confabulation
fixture, since it demonstrates the failure with a correct headline answer
and a fabricated justification — a stronger, more misleading case than an
outwardly wrong answer. A generic fallback checker handles problem classes
with no registered domain-specific verifier, labeling their output
"provisional" rather than passing it through unchecked.

## Consequences

- Adds one new harness-owned module category (deterministic verification)
  and one schema extension to existing wire-contract validation — no new
  parallel validation system.
- Adds latency (plan rejection/redraft, verification, possible retries)
  for requests in this class. Accepted: a slower, honestly-labeled answer
  is preferred to a fast, silently wrong or silently unverifiable one.
- P0 means some sessions will bounce a plan back to sys2 before any
  execution happens at all — this is visible to the user as an extra
  round-trip, and should be surfaced as such (not hidden inside
  "[working...]") so it doesn't look like a stall.
- Problem classes with no closed-form witness (open-ended optimization,
  for instance) fall back to the P4 provisional-label path rather than
  being blocked indefinitely.

## Alternatives Considered

- **Witness capture and post-hoc verification only, no plan-time gate**
  (the second-reviewer proposal as originally scoped). Rejected as
  insufficient on its own: it detects a bad answer after the fact but
  does nothing to make a correct one more likely to occur before
  execution runs, which was the failure mode in the first observed
  session.
- **Witness for positive answers only.** Rejected: an unproven "NO" is
  exactly as ungrounded as an unproven "YES," and the instance used for
  testing was specifically constructed to make false negatives easy to
  produce via an incomplete search.
- **Have sys1 grade sys2's output.** Rejected, unchanged from v1 — sys1 is
  a non-generative single-pass classifier; exact combinatorial grading is
  not its job.
