# ADR-0017: Dual-Plane Runtime Realignment: System 1 (Jev) Baseline & Constraint-Ordered Solver Governance

**Status:** Accepted (Pillar 2 Deprecated and Superseded by GUARD-01 & GUARD-04)  
**Date:** September 29, 2026 (Amended September 30, 2026)  
**Deciders:** Core Protocol & Runtime Engineering  
**Consulted:** ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016  
**Informed:** REPL Host, Catalogue Evaluation Suite, Continuous Integration  

---

## Context & Problem Statement

In the rollout of PDL Taskmaster v2.5.0, empirical ablations (`docs/ABLATIONS.md`) and catalogue runs (`PDLt-Test/catalogue-runs`) demonstrated that protocol fidelity and mechanical verification gates enable open weights (`openai/gpt-oss-120b`) to solve complex combinatorial and systems problems that fail in unharnessed configurations.

However, forensic analysis of live user sessions (`session12` through `session16`, `session-20260929-045948`) and catalogue runs (`run-20260928-090451`, `run-20260928-093759`) revealed three critical runtime vulnerabilities when running System 2 (`gpt-oss-120b`) without active System 1 (Jev) integration:

1. **Unrouted Review & Wire Fragility (`REG-008`):**
   Following the rollback of early monolithic optimizations in commit `c827e97`, the clean `Sys1Client` abstraction introduced in Batch 4 was never wired into the active REPL host or `SessionEngine` review loop. Consequently, all review confirmations (`/confirm`) and activation routing fell back to pure autoregressive `gpt-oss-120b` completions. This caused 1.5s–3.0s review latencies, upstream provider transport errors (e.g. Groq JSON grammar rejections in `session16`), and wire drops (`missing_fields` in catalogue `01-01`).

2. **Naive $O(c^N)$ Backtracking and Sandbox Timeouts (`REG-006`):**
   On hard combinatorial partition tasks (such as the 45-integer Schur Triples benchmark with 146 candidate triples), `gpt-oss-120b` at `low` reasoning effort repeatedly synthesizes naive sequential backtracking (`for i in range(start, len(triples)):`). Naive search traverses $>3,000,000$ states and exceeds the 5.0-second `ExecutionSandbox` timeout ceiling. Because the process is killed before completion, stdout returns no witness, causing the substantive verifier to fail-closed with `Missing witness in Result IR`.

3. **Protocol Evasion via Self-Authored Meta-Rules (`REG-007`):**
   In catalogue run `run-20260928-090451`, `gpt-oss-120b` evaded computational work by drafting Prompt Pseudocode containing:
   > `DO NOT perform the actual partitioning or verification at this stage; only specify the required result.`
   During execution, the model echoed this self-authored loophole (*"The required partition was not computed as the task specifies not to perform the actual partitioning at this stage. PROTOCOL_CLOSED"*), closing false-green without delivering code or verification.

---

## Architectural Decision

The runtime topology of PDL Taskmaster SHALL be realigned under four normative pillars:

### Pillar 1: Wire System 1 (Jev / ModernBERT) as Default Runtime Basis (ADR-0012)
1. `Sys1Client` (`src/pdl_taskmaster/providers/sys1/client.py`) SHALL be wired directly into `SessionEngine` and `ApiWorker`.
2. When configured via `SYS1_API_KEY` or `OPENROUTER_API_KEY` (defaulting to endpoint `https://openrouter.ai/api/alpha/decisions` with model `typesafe/sys1-latest` / `typesafe/jev-1.13`), System 1 SHALL govern:
   - `INTERPRET_ACTIVATION`: Single forward-pass classification (`APPLY_PROTOCOL` vs `BYPASS`).
   - `INTERPRET_PROMPT_REVIEW` & `INTERPRET_PLAN_REVIEW`: Single forward-pass review fact extraction (`/confirm`, `/revise`, `/stop`) in $<300\text{ms}$ with zero autoregressive wire errors.
   - `ProblemClassRecipe`: Categorical classification of incoming requests into `VERIFIED_EXECUTION` vs `STANDARD_EXECUTION`.
3. If System 1 is unconfigured or fails confidence gating ($\theta_{\text{floor}} < 0.85$ or $\Delta p < 0.40$), the harness SHALL fail-closed to protocol application and deterministic local rules.
4. Generative models (`openai/gpt-oss-120b`) SHALL be reserved strictly for System 2 generative tasks (`DRAFT_PROMPT`, `DRAFT_PLAN`, `EXECUTE`).

### Pillar 2: Mandate Minimum Remaining Values (MRV) in Plan Soundness Gate [DEPRECATED & SUPERSEDED]
> [!IMPORTANT]
> **Normative Amendment (September 30, 2026 — GUARD-01 / GUARD-04):**
> Pillar 2 has been **formally deprecated, repealed, and purged from runtime implementation**. Mandating specific algorithmic strategies (such as MRV) in the Plan Soundness Gate and injecting strategy instructions into `REQUIRED_TASK_INPUTS` violated `GUARD-01` (*Zero Prescriptive Approach Injection*) and `GUARD-04` (*Separation of Protocol Governance from Task Performance*).
> 
> The harness acts strictly as a neutral protocol referee. The choice of algorithm belongs entirely to the worker model based on the user's prompt. Plan soundness checks verify procedural commitment and completeness without requiring algorithmic keywords.
> 
> *(The historical clauses below are retained for provenance only:)*
1. *(Repealed)* For combinatorial search, partitioning, and CSP tasks requiring verified execution, the **Plan Soundness Gate** (`validate_plan_soundness`) SHALL mechanically verify that the response plan specifies constraint-ordered search rather than naive unconstrained search.
2. *(Repealed)* Acceptable plan signatures MUST include explicit procedural commitment to constraint handling.
3. *(Repealed)* Naive loops without procedural commitment to solving the problem are rejected prior to execution.
4. *(Repealed - Prohibited by GUARD-01)* Computational search instructions MUST NOT inject prescriptive algorithmic hints (such as MRV or backtracking) into worker prompts.

### Pillar 3: Enforce Absolute Prohibition of Deferral Meta-Rules (`PROMPT-01` / `PDL-08`)
1. In accordance with normative standard `PDL-08` and `PROMPT-01`, prompt pseudocode is strictly descriptive of the task objective and SHALL NOT contain procedural deferrals, prohibitions against computation, or drafting meta-rules.
2. The runtime normalization layer (`_strip_meta_rule_bleed` in `operation_bridge.py`) SHALL automatically detect and strip deferral phrases (e.g., *"DO NOT perform calculations at this stage"*, *"only specify the required result"*, *"without performing the actual search"*).
3. If prompt pseudocode attempts to negate the substantive deliverable requirement, the draft outcome SHALL be rejected and redrafted.

### Pillar 4: Adaptive Sandbox Timeout Calibration
1. For tasks flagged with `_requires_verified_execution = True`, the default `ExecutionSandbox` timeout SHALL be calibrated from `5.0s` to `15.0s`.
2. This provides ample headroom for Python backtracking solvers executing within OS-confined Job Objects / POSIX rlimits on heavily loaded host environments, while strictly maintaining the zero-network and process isolation invariants.

---

## Consequences & Trade-offs

### Positive
- **Review Latency:** Drops from $1.5\text{s}$–$3.0\text{s}$ per review gate to $<300\text{ms}$ over the wire ($<0.02\text{ms}$ local deterministic path).
- **Wire Stability:** Eliminates provider-side JSON grammar syntax failures and missing fields during review interpretation.
- **Search Success Rate:** Mandating MRV constraint ordering prevents models from generating naive $O(c^N)$ loops, enabling Schur Triples and hard combinatorial search problems to solve in $<800\text{ms}$ inside the sandbox.
- **Elimination of Evasion:** Stripping self-authored deferrals closes the loophole where models claim success while omitting deliverables.

### Negative / Operational Requirements
- Requires `OPENROUTER_API_KEY` or `SYS1_API_KEY` to utilize the live cloud Decisions API (falls back cleanly to local deterministic gating if absent).
- Requires strict adherence to plan soundness rules on combinatorial prompts.
