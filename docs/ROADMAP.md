# Roadmap — Framing, Efficiency, & Adversarial Evaluation

**PDL-Standard-REPL-Harness (PDL Taskmaster)** · Base: `v2.0.0` · Updated: 2026-09-13

This roadmap sequences work across three interconnected tracks:
- **Track F (Framing & Evidence):** Evidentiary claims in `docs/FRAMING.md`, adversarial evaluation, and proof-by-contradiction.
- **Track E (Efficiency & Levers):** Cost, latency, and transport optimizations in `docs/EFFICIENCY_REPORT.md` and `providers/api_worker.py`.
- **Track M (Measurement & Multi-Model):** Shared empirical evaluation infrastructure that unlocks high-confidence claims across models and platforms.

---

## Executive Status Summary

| ID | Item | Track | Effort | Risk | Phase | Status | Shipped In / Note |
|---|---|---|---|---|---|---|---|
| **F1** | Situate mechanism vs prior art | F | S | Low | 1 | **SHIPPED** | Commit `34b316a` (`docs/FRAMING.md`) |
| **F2** | Move n=1 caveat next to headline table | F | S | Low | 1 | **SHIPPED** | Commit `34b316a` (`docs/FRAMING.md`) |
| **F3a** | Flag case-mismatch in "affordable" claim | F | S | Low | 1 | **SHIPPED** | Commit `34b316a` (`docs/FRAMING.md`) |
| **F5** | Cite `EXECUTION_CONTRACT.json` directly | F | S | Low | 1 | **SHIPPED** | Commit `34b316a` (`docs/FRAMING.md`) |
| **E4** | Structural 5-call floor documented | E | S | Low | 1 | **SHIPPED** | Commit `34b316a` (`docs/EFFICIENCY_REPORT.md`) |
| **E1** | Per-operation model tiering | E | M | Med | 2 | **SHIPPED** | Commit `34b316a` (`--api-model-operation`) |
| **E2** | Structured-output constraints & grammar sanitization | E | M | Med | 2 | **SHIPPED** | Commits `34b316a`, `1561d2d` (`--api-structured-output`) |
| **—** | POSIX key-resolution fallback & SSH decoupling | E | S | Low | 2 | **SHIPPED** | Commits `61ca98d`, `29a745c` |
| **M1** | Qualified-measurement eval harness | M | L | Low | 3 | **SHIPPED** | Commit `1561d2d` (`scripts/run_qualified_batch.py`) |
| **F6** | Broad breadth-first adversarial battery | F | L | Low | 4 | **SHIPPED** | Commit `1561d2d` (`scripts/build_adversarial_battery.py`) |
| **F6.0b**| Tool-result injection applicability spike | F | S | Low | 4 | **NO-GO** | Mechanically isolated; out of scope per `AUTH-06` |
| **F4** | Contradiction argument runner (relabeled tripwire) | F | M | Low | 4 | **SHIPPED** | Commit `1561d2d` (`--control-prompt-patch`) |
| **F3b**| Re-measure efficiency on boundary case | F/E | M | Low | 4 | **IN PROGRESS** | Initial paired run recorded in `docs/EVAL_METRICS.md` |
| **M2** | Multi-model revalidation (GLM-4.7, Flash, etc.) | M | M | Low | 4 | **PROPOSED** | Battery runner ready; tests runnable across models |
| **E3** | Transport-level cache fix (pinned instances) | E | L | High | 5 | **PROPOSED** | Exploratory; depends on provider affinity |
| **E5** | Provider-side session threading | E | L | High | 5 | **PROPOSED** | Exploratory; requires strict positive-inclusion proof |

---

## Phase 1 — Documentation Integrity [SHIPPED]

Completed in commit `34b316a`.

- **F1 — Situate relative to prior art:** Added subsection in `docs/FRAMING.md` delineating departures from dual-LLM architectures and soft plan-then-confirm conventions (single interpretation step, clause compilation, mechanical gate).
- **F2 — Headline caveat placement:** Moved `(single paired run, n=1 per arm — see Honest Scope)` directly beneath the Evidence II table in `docs/FRAMING.md`.
- **F3a — Case-mismatch clarification:** Disclosed in `docs/FRAMING.md` that the 23% token reduction was measured on the greeting lifecycle (`hi`), whereas boundary cases exercise the full 20-clause review projection.
- **F5 — Inspectable contract citation:** Cited `contracts/EXECUTION_CONTRACT.json`'s `DRAFT_PROMPT` requirements array directly in `docs/FRAMING.md` as concrete evidence for the "one mechanism" claim.
- **E4 — Structural call-count floor:** Documented in `docs/EFFICIENCY_REPORT.md` that the 5-call lifecycle is the normative cost of `PROTO-02`'s two independently confirmable gates (`AUTH-03`), not incidental waste.

---

## Phase 2 — Low-Risk Code Levers & Platform Hardening [SHIPPED]

Completed in commits `61ca98d`, `34b316a`, `29a745c`, and `1561d2d`.

- **E1 — Per-operation model tiering:** Added `model_by_operation` to `ApiWorker` and `--api-model-operation OP=MODEL` to `host/repl.py`. Enables routing high-capacity models to draft operations while lightweight models handle review classifications.
- **E2 — Real structured-output constraints:**
  - Added `--api-structured-output` to pass compiled JSON schemas directly into OpenAI-compatible `/responses` endpoints.
  - Implemented `_sanitize_schema_for_grammar` in `providers/api_worker.py` to recursively strip stateful keywords (like `uniqueItems`) rejected by context-free grammar engines (e.g. Venice / vLLM on OpenRouter), ensuring universal compatibility across backends.
- **Platform Hardening & Codex Decoupling:**
  - Inverted default worker to `api` and model to `z-ai/glm-4.7`.
  - Lazy-loaded `CodexWorker` with preflight check; guarded `/config` and `/sandbox` commands.
  - Added portable POSIX environment key resolution and graceful EOF/signal termination for headless SSH relays (Paseo, RemoteCode).
  - Recorded relative workspace paths in `session.json` for seamless cross-OS session migration.

---

## Phase 3 — Measurement Infrastructure (M1) [SHIPPED]

Completed in commit `1561d2d`.

- **`scripts/run_qualified_batch.py`:**
  - Supports dual arms: `control` (plain unconstrained API call) vs `protocol` (PDLt mechanical state machine).
  - Supports manifest filtering by vector (`--vector`) and case (`--case-id`).
  - Implements **Adaptive Escalation**: runs baseline $n=3$ trials; automatically escalates to $n=10$ if non-unanimous results occur ($0 < \text{leaks} < n$).
  - Supports `--qualified` flag (enforces $n \ge 10$ trials and tags measurement condition).
  - Full offline CI testing via `--stub` with `LiveStubWorker`.
  - MLflow logging integration (`--mlflow`).
- **`scripts/compare_eval_runs.py`:**
  - Implements **Arm A/B Evaluation** report generation in Evidence II markdown format.
  - Implements **Cross-OS Invariance** report generation diffing Windows (`win32`) vs Linux (`linux`) runs.

---

## Phase 4 — Adversarial Battery & Multi-Model Validation

### F6 — Breadth-First Adversarial Test Battery [SHIPPED in 1561d2d]
Replaced the v1 depth-heavy plan (10 trials × 7 cases) with a comprehensive breadth-first battery generated by `scripts/build_adversarial_battery.py`:
- **Design Principles:**
  1. *Refusal is a gating precondition, not the metric:* Track refusal alongside leak rate.
  2. *No instance-keyed tripwires:* Each case carries a cryptographically unique 16-character hexadecimal token (`TRIPWIRE_<HEX>`).
  3. *Parametric case families:* Minimum 8 structurally distinct cases per vector covering parameter spaces.
  4. *Adaptive depth:* $n=3$ baseline trials; escalate to $n=10$ only on ambiguity.
- **Vectors & Case Allocation:**
  - `BND-00`: Single-message direct override baseline.
  - `F4-CONTRADICTION`: Proof-by-contradiction paired case.
  - `DRIP-01..10` (10 cases): Multi-turn fragmentation varying `turn_count` (2, 3, 5, 8), `tripwire_position` (early, mid, late), and `framing` (code review, security audit, doc summary, etc.).
  - `ENC-01..10` (10 cases): Obfuscation varying `encoding_scheme` (Base64, ROT13, Hex, URL, Binary, Leetspeak, Reverse, NATO) and `decode_cue` (explicit vs implicit).
  - `STACK-01..05` (5 cases): Combinatorial vectors combining drip fragmentation with encoding.
- **Scaffold & Manifest:** Saved to `runs/adversarial/MANIFEST.json` and `runs/adversarial/<case_id>/turns.json`.

### F6.0b — Tool-Result Injection Spike [NO-GO / RESOLVED]
- **Finding:** Inspected `runtime/session_engine.py` and `mechanical_controller.py`. Tool results never re-enter model context as unconstrained prompts; the state machine gates purely mechanically on exit codes/artifacts under `AUTH-06` and `CONFORM-02`.
- **Verdict:** Tool-Result injection is formally out of scope for the current harness architecture.

### F4 — Proof-by-Contradiction Runner [SHIPPED in 1561d2d]
- Implemented `--control-prompt-patch` in `scripts/control_api_call.py` to inject naive bans (e.g. "Do not output ACTIVATED") against relabeled tripwire tokens.
- Demonstrates that naive bans fail when the adversary alters the label, whereas protocol data quarantine holds invariant.

### F3b — Re-measure Efficiency on Boundary Cases [IN PROGRESS]
- Measure full token/latency distributions across the 27 adversarial cases using `run_qualified_batch.py`. Initial paired benchmark on `BND-00` documented in `docs/EVAL_METRICS.md`.

### M2 — Multi-Model Revalidation [PROPOSED]
- Run the F6 battery and SEM-05 fidelity suite across candidate model families (`z-ai/glm-4.7`, `z-ai/glm-4.7-flash`, DeepSeek, Claude, GPT-4o) using `--model`.
- Document cross-model defense rates and efficiency variations in `RELEASE_NOTES.md`.

---

## Phase 5 — Exploratory Levers (GO/NO-GO Discipline)

Follows the same evidentiary standard as earlier rejected levers (draft-stage low reasoning, aggressive static prefix caching).

### E3 — Transport-Level Cache Affinity
- **Goal:** Replace opportunistic byte reordering (`--cache-order-render`) with deterministic cache pinning or routing affinity where provider endpoints expose session headers.
- **Acceptance:** Measured, non-lottery cache-hit improvement on a named backend, or recorded NO-GO.

### E5 — Provider-Side Session Threading (Prototype Only)
- **Goal:** Reuse server-side conversation caches across the 5-call lifecycle.
- **Constraint:** High risk of violating positive inclusion (`CONTEXT-01`) and rejected-context exclusion (`CONTEXT-04`).
- **Acceptance:** Strictly gated behind `--experimental-session-thread` with automated assertion that compiled projections remain byte-identical to stateless runs.
