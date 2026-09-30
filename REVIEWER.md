# Reviewer Navigation Guide: PDL Standard REPL Harness (`pdlt`)

> **For LLM Reviewers & Auditors**: Read this file first. It is an index of where critical logic lives and what files to **ignore** so you do not waste context tokens on noise.

---

## 1. System in 30 Seconds

The harness (`pdl-taskmaster`) is a deterministic protocol referee and dual-plane runtime governor enforcing the Prompt Declaration Language standard (`PDL-01`..`PDL-08`):
1. **Router (System 1)**: <200ms discrete classifier for policy boundaries, network checks, and review intent.
2. **Solver (System 2)**: Frontier LLM generating prompt pseudocode, plan pseudocode, and deliverables.
3. **Verifier (Deterministic Engine)**: Pydantic-first schema validation and host sandbox execution.

**The Golden Invariant**: The harness is a referee, NEVER a solver. It must not inject algorithmic coaching (e.g. MRV, DLX, backtracking hints), enforce algorithmic keywords in review gates, or fabricate witnesses. A failed benchmark is diagnostic; a gamed pass is an integrity defect.

---

## 2. File Map: What Matters (Read These)

Focus your review on these core paths:

| Component | Path | Key Files & Responsibility |
|---|---|---|
| **State Machine** | `src/pdl_taskmaster/runtime/` | `session_engine.py`: Stage transitions (`PROMPT_REVIEW` $\to$ `PLAN_REVIEW` $\to$ `EXECUTION` $\to$ `CLOSED_SUCCESS`). Prompt assembly without synthetic hints.<br>`result_ir.py`: Deliverable & witness data structures. |
| **Verification** | `src/pdl_taskmaster/verification/` | `output_verifier.py`: Schema validation & witness extraction (ADR-0018).<br>`plan_soundness.py`: Grammar & structural validation of PDL rules.<br>`sandbox.py`: Isolated host execution with timeouts and memory limits.<br>`checkers/partition_sum_triples.py`: Deterministic partition checker. |
| **System 1 Router** | `src/pdl_taskmaster/providers/sys1/` | `fast_router.py`: Dual-Plane classifier orchestration.<br>`recipes/activation_route.py`: General boundary refusal (scope, network, cutoff).<br>`recipes/problem_class.py`: Task classification.<br>`recipes/review_intent.py`: Gate confirmation parsing (`CONFIRM`, `REVISE`, `CANCEL`). |
| **Worker Client** | `src/pdl_taskmaster/providers/` | `api_worker.py`: System 2 LLM inference client (`gpt-oss-120b`). |
| **Normative Contracts** | `contracts/` | Canonical JSON schemas and `CONTRACT_MANIFEST.json` (tracked with SHA-256 hashes). |
| **Integrity Gate** | `tests/` | `test_harness_anti_overfitting.py`: 10 automated regression checks for anti-coaching, benchmark contamination, and contract sync. |
| **Normative SSOT** | `docs/guardrails/` | `ANTI_OVERFITTING_AND_BENCHMARK_INTEGRITY.md`: Authoritative protocol guardrails (`GUARD-01` to `GUARD-05`). |
| **Agent Rules** | `AGENTS.md` | Primary operational contract for coding assistants. |

---

## 3. What to Ignore (Skip - Do Not Waste Context)

Do NOT load these directories during architectural or code reviews:

| Path | Reason to Skip |
|---|---|
| `docs/pdlt-docs/` | Historical notes, early scratchpads, and superseded draft transcripts. |
| `docs/adr/` | Historical decisions at frozen points in time. If any ADR conflicts with `docs/guardrails/`, the guardrail wins. |
| `confirm-with-pseudocode/` | Legacy proof-of-concept archive. |
| `runs/` & `mlruns/` | Telemetry logs, traces, and run artifacts. |
| `scratch/` | Ephemeral debugging scripts. |
| `dist/`, `.venv/`, `__pycache__/` | Ephemeral build and Python runtime artifacts. |

---

## 4. Key Architectural Invariants

- **No Prompt Coaching (`GUARD-01`, `GUARD-04`)**: The engine must never inject algorithmic advice into `carried` approaches or error messages.
- **Physical Boundary Routing, Not Plan Grading (`GUARD-02`)**: System 1 routes permissions and environment conditions; it does NOT qualitatively grade plan completeness or reasoning style.
- **Pydantic SSOT (`GUARD-03`, ADR-0018)**: No regex scraping of deliverable text. Analytical proofs and symbolic deductions are first-class deliverables without Python code.
- **Zero Benchmark Contamination**: No benchmark prompt IDs (`01-01`..`15-07`) or fixture names (`frostbitedb`) in `src/`.

---

## 5. Quick Verification Commands

```powershell
# 1. Mandatory anti-overfitting gate (<1s)
pytest tests/test_harness_anti_overfitting.py -v

# 2. Live REPL protocol baseline (<5s)
pdlt verify

# 3. Offline test suite (~2m)
pytest -m "not slow and not live"
```
