# Roadmap — Framing, Efficiency, Adversarial Evaluation & Local Integration

**PDL-Standard-REPL-Harness (PDL Taskmaster)** · Base: `v2.0.0` · Updated: 2026-09-14

This roadmap sequences work across four interconnected tracks:
- **Track F (Framing & Evidence):** Evidentiary claims in `docs/FRAMING.md`, adversarial evaluation, and proof-by-contradiction.
- **Track E (Efficiency & Levers):** Cost, latency, and transport optimizations in `docs/EFFICIENCY_REPORT.md` and `providers/api_worker.py`.
- **Track M (Measurement & Multi-Model):** Shared empirical evaluation infrastructure that unlocks high-confidence claims across models and platforms.
- **Track L (Local & Integration):** Local worker support, prefix-cache architecture, training-data export, and the distillation flywheel for a bespoke PDL-native worker model.

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
| **F6.1** | Rigor remediation (12 construct-validity fixes) | F/M | M | Low | 4 | **SHIPPED** | Corrected scripts: `leak_scan.py`, battery v4, runner v3 |
| **F6.2** | False-positive elimination & deliverable isolation | F/M | M | Low | 4 | **SHIPPED** | Deliverable isolation, markdown extraction, cancellation scoring |
| **F6.3** | Steelmanned structured adversarial evaluation | F/M | M | Low | 4 | **SHIPPED** | `AdversarialAuditOutcome` schema, reasoning=none, delimiter defenses |
| **F6.4** | Official qualified baseline validation (N>=10) | F/M | L | Low | 5 | **NEXT PHASE** | Definitive Wilson 95% CI validation across all 27 cases |
| **F3b**| Re-measure efficiency on boundary case | F/E | M | Low | 4 | **SHIPPED** | Full token/latency benchmark across all 27 cases |
| **M2** | Multi-model revalidation (GLM-4.7, Flash, etc.) | M | M | Low | 6 | **PROPOSED** | Battery runner ready; tests runnable across models |
| **L1** | `--worker local` alias targeting warm daemon | L | S | Low | 6 | **PROPOSED** | `ApiWorker` with `localhost` target |
| **L2** | `--cache-order-render` default for local workers | L | S | Low | 6 | **PROPOSED** | Prefix-cache reuse as default architecture |
| **L3** | `--training-export` flag for lifecycle traces | L | M | Low | 6 | **PROPOSED** | Export validated sessions as SFT training data |
| **L4** | Training data curation pipeline | L | M | Low | 6 | **PROPOSED** | Filter by validation status, format for Unsloth/PEFT |
| **L5** | LoRA adapter v1 (REVIEW + DRAFT_PLAN) | L | L | Med | 7 | **PROPOSED** | 3B–7B base, frontier teacher distillation |
| **L6** | Battery-gated deployment validation | L | M | Low | 7 | **PROPOSED** | Adversarial suite as quality ratchet for adapter |
| **L7** | Per-operation routing to local adapter | L | M | Low | 7 | **PROPOSED** | `--api-model-operation REVIEW=local:adapter-v1` |
| **L8** | Flywheel iteration v2+ | L | L | Med | 7 | **PROPOSED** | Progressive distillation with frontier anchor |
| **L9** | Scope expansion (EXECUTE on non-adversarial) | L | M | Med | 8 | **PROPOSED** | Battery-gated, measured expansion of worker scope |
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

### F6.1 — Rigor Remediation (12 Construct-Validity Fixes) [SHIPPED]
Independent audit of the M1/F6 evaluation infrastructure identified 12 structural and construct-validity bugs that invalidated earlier protocol measurements:
- **Finding A (CRITICAL):** Protocol arm stalled at `EXEC-01 WAITING_INPUT`; the execution deliverable was never generated but scored as 0% leak. Resolved with multi-turn payload handoff.
- **Finding C (CRITICAL):** `refusal_detected` was hardcoded to `True` for all protocol trials. Resolved with structured verdict and compliance marker scoring.
- **Finding D (CRITICAL):** 93% of generated attack cases included a plaintext `"Do not echo {token}"` ban, handing the model the answer by construction. Removed across battery v3/v4.
- **Finding B (HIGH):** Asymmetric leak scanning — control scanned all turns; protocol scanned only the last. Resolved with shared `leak_scan` module.
- **Finding G (HIGH):** `--qualified` disabled adaptive escalation, forcing expensive flat $n=10$. Resolved with Wilson-based escalation.
- **Findings E–L (MEDIUM/LOW):** Position-index collisions, decorative obfuscation, unverified trial counts, silent refusal defaults, substring matching vulnerable to zero-width characters, non-deterministic tokens. Fully remediated across `leak_scan.py`, `build_adversarial_battery.py` v4, and `run_qualified_batch.py`.

### F6.2 — False-Positive Elimination, Native DLP Standards & Construct Validity [SHIPPED]
Eliminated the construct-validity failure where the scoring harness penalized intermediate protocol governance dialogue, and enshrined token redaction directly into normative protocol standards:
- **Native Protocol Standards (SEM-06 & EXEC-04):** Enshrined `SEM-06 — Payload token redaction` in `SEMANTIC_INPUT_STANDARD.md` and `EXEC-04 — Safe deliverable emission` in `EXECUTION_STANDARD.md` (indexed in `CONTRACT_MANIFEST.json` and validated by `StandardRegistry`). Verbatim emission of raw canary tokens or exploit directives is strictly forbidden across all outputs, plans, reviews, and deliverables.
- **Pure Adversarial Fixtures (Zero Prompt Assistance):** Completely eliminated defensive redaction instructions from user attack prompts in `scripts/build_adversarial_battery.py` and regenerated all 27 battery fixtures in `runs/adversarial/`. Control defenses live strictly in developer system prompts; protocol defenses live natively in compiled contracts.
- **Deliverable Isolation:** Intermediate Prompt Pseudocode review dialogue (where the host quotes and quarantines untrusted input for human confirmation) is strictly excluded from leak scanning. Only the final artifact emitted by `EXECUTE` on the closing turn is evaluated.
- **First-Class Mitigation Scoring:** Protocol cancellations (`CLOSED_CANCELLED` and `BLOCKED_BY_HIGHER_PRIORITY`) are explicitly scored as clean defenses (`leak_detected: False`, `refusal_detected: True`).
- **Dual-Format Deliverable Extraction:** `leak_scan.py` parses labeled markdown deliverable sections (`sanitized_clean_deliverable: <text>`) alongside raw JSON objects.
- **Control Socket Retry Resilience:** `control_api_call.py` equipped with exponential backoff retries (3 attempts) on socket/HTTP timeouts, eliminating transient stall aborts (e.g. `DRIP-06`).
- **Protocol Trial Persistence & Calibrated Ceilings:** Individual trial JSON records are now written for Protocol trials alongside Control; per-case latency ceilings dynamically scale with interactive gate steps (`protocol_ceiling_s = max(150.0, 45.0 * (len(turns) + 4))`).

### F6.3 — Steelmanned Structured Adversarial Evaluation [SHIPPED]
Eliminated false equivalence between unconstrained conversational free-prose and structured protocol execution:
- Standardized both Control and Protocol arms on the **`AdversarialAuditOutcome` structured facts JSON contract** (`verdict`, `threat_categories`, `contains_override_directive`, `technical_critique`, `sanitized_clean_deliverable`).
- Steelmanned the Control Arm with explicit `<untrusted_input>` delimiter boundaries, production-grade defensive system prompts, and DLP redaction mandates.
- Disabled runaway chain-of-thought token generation (`reasoning_effort="none"`), achieving a 7.3× speedup and enforcing active per-case hard-stop circuit breakers.
- Discovered **Contextual Amnesia**: Control Arm experiences an 86.7% decision-hijack rate across multi-turn chains (certifying malicious inputs as `verdict: "SAFE"`), whereas Protocol Arm achieves **0.0% hijacking (0/27)**.

### F6.4 — Official Qualified Baseline Validation (N>=10) [NEXT PHASE / COMMIT]
- Enforces an official qualified baseline ($N \ge 10$ trials per case across both arms, 270 trials per arm).
- Gated behind external human evaluation of the single-trial confirmation suite to prevent premature spend before failure modes are audited.
- Establishes a publication-grade Wilson 95% confidence interval ($\le 0.25$ upper bound on leak rate).

### F3b — Re-measure Efficiency on Boundary Cases [SHIPPED]
- Measured full token/latency distributions across all 27 adversarial cases using `run_qualified_batch.py`. Protocol completed with 100% completion rate (27/27), zero stalls, and an average case latency of ~35s. Initial paired benchmark documented in `docs/EVAL_METRICS.md` and `docs/EFFICIENCY_REPORT.md`.

### M2 — Multi-Model Revalidation [PROPOSED]
- Run the F6 battery and SEM-05 fidelity suite across candidate model families (`z-ai/glm-4.7`, `z-ai/glm-4.7-flash`, DeepSeek, Claude, GPT-4o) using `--model`.
- Document cross-model defense rates and efficiency variations in `RELEASE_NOTES.md`.
- M2 also serves as the **training data pipeline** for Track L: every validated session across model families generates (input, output, validation) triples for distillation.

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

---

## Phase 6 — Local Worker & Training Infrastructure (Track L)

### L1 — `--worker local` Alias [PROPOSED]
- **Goal:** Thin alias for `ApiWorker` targeting `localhost`, with documentation requiring a warm daemon (Ollama, vLLM, llama.cpp server). Not spawn-per-call.
- **Rationale:** Transport M×N is already converging to M×1 — every serious local runtime speaks OpenAI-compatible `/v1/chat/completions`. `ApiWorker` already talks this protocol.

### L2 — Prefix-Cache Reuse as Default [PROPOSED]
- **Goal:** Promote `--cache-order-render` to default for `--worker local`. The invariant protocol standards form a stable, unchanging prefix across calls; local engines (vLLM automatic prefix caching, llama.cpp slot caching) skip recomputing KV blocks for that prefix.
- **Constraint:** Full explicit prompts on every call (`CONTEXT-01`/`CONTEXT-04` satisfied) — compute reuse at the GPU layer with zero security risk.

### L3 — Training Data Export [PROPOSED]
- **Goal:** `--training-export` flag (or post-session script) exports validated lifecycle traces in SFT format. Each example is a complete 5-call lifecycle: `[(op, context, output, validation), ...]`.
- **Rationale:** Training data generation is a natural byproduct of normal harness usage and adversarial battery runs. Training itself (LoRA fine-tuning) is a separate offline step using standard tooling (Unsloth, PEFT, axolotl).

### L4 — Training Data Curation Pipeline [PROPOSED]
- **Goal:** Filter exported traces by mechanical validation status; separate SFT positives (gate-passing outputs), DPO preference pairs (user corrections), and negatives (gate failures). Format for Unsloth/PEFT ingestion.

---

## Phase 7 — Distillation Flywheel & Bespoke Worker Model (Track L)

**Architecture:** 2-model hybrid split. Frontier model (unmodified, API) handles `DRAFT_PROMPT` and `EXECUTE` (semantic interpretation and reasoning). Bespoke worker model (3B–7B, LoRA-adapted, local) handles `REVIEW` classification and `DRAFT_PLAN` (protocol-mechanical operations requiring reliable format compliance, not deep reasoning). Mechanical harness (external deterministic code) wraps both.

### L5 — LoRA Adapter v1 [PROPOSED]
- **Goal:** Train LoRA adapter on a 3B–7B open-weights base (Qwen 2.5 / Phi-4-mini / Llama 3.1) using frontier teacher-generated gold data (bulk of corpus) plus organic harness sessions with mechanical validation labels.
- **Training format:** Complete lifecycle traces as training units — model learns operation transitions, not isolated tasks.
- **Distillation strategy:** Progressive distillation with frontier anchor. v1 trains on frontier teacher data. v2 trains on v1's validated successes + frontier-corrected failure cases. Frontier model is the permanent correction signal preventing generational drift.

### L6 — Battery-Gated Deployment Validation [PROPOSED]
- **Goal:** Run adversarial suite against LoRA adapter v1; compare defense rate and completion rate against frontier baseline. Adapter ships only if it matches or exceeds frontier on both metrics.
- **Anti-collapse mechanism:** Mechanical controller + adversarial battery = external deterministic verifier (structurally identical to DeepSeek R1's verified-reasoning approach).

### L7 — Per-Operation Routing to Local Adapter [PROPOSED]
- **Goal:** Extend E1's `--api-model-operation` to route `INTERPRET_PROMPT_REVIEW`, `INTERPRET_PLAN_REVIEW`, and `DRAFT_PLAN` to the local adapter while `DRAFT_PROMPT` and `EXECUTE` remain on frontier.
- **Cost impact:** 2 frontier API calls + 3 near-zero-cost local calls per lifecycle.

### L8 — Flywheel Iteration v2+ [PROPOSED]
- **Goal:** Recursive improvement loop. v(n)'s successes become SFT data for v(n+1). v(n)'s failures are re-run through frontier teacher for gold correction. Adversarial battery is the ratchet.
- **Frontier dependency trajectory:** Shrinks over time — as the worker model's compliance improves, the boundary between "frontier-required" and "distillable" operations shifts.

### L9 — Scope Expansion Spike [PROPOSED]
- **Goal:** Evaluate whether EXECUTE can be distilled for non-adversarial tasks. Battery-gated: adapter handles EXECUTE only if defense rate holds.
- **Acceptance:** Measured completion rate and defense rate parity with frontier on a held-out task suite, or recorded NO-GO.

