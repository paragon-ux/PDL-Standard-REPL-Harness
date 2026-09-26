# TRD-0002: Controller-Gated Pseudocode Protocol with Out-of-Band Structural Containment and Bounded Reasoning

> **Provenance note (v2.3.0 repo restructure, appended):** Standards references written as `../standards/<NAME>.md`
> reflect the pre-restructure layout; the normative standards now live at `contracts/standards/`. Links are left
> as ratified; body text is preserved verbatim per the append-only provenance policy.

- Status: Accepted / Active
- Version: 1.0
- Date: 2026-09-16
- Supersedes: [TRD-0001: Controller-gated pseudocode protocol](0001-controller-gated-pseudocode-protocol.md)
- Governing decisions:
  - [ADR-0001: Adopt a controller-gated pseudocode protocol](../adr/0001-controller-gated-pseudocode-protocol.md)
  - [ADR-0002: Use controller-owned artifact controls](../adr/0002-controller-owned-artifact-controls.md)
  - [ADR-0003: Use phase-projected single-model contexts](../adr/0003-phase-projected-single-model-contexts.md)
  - [ADR-0004: Make confirmed artifacts the clean execution boundary](../adr/0004-confirmed-artifacts-as-execution-boundary.md)
  - [ADR-0005: Support optional Result Pseudocode](../adr/0005-optional-result-pseudocode.md)
  - [ADR-0006: Bound pre-execution reasoning and material guessing](../adr/0006-bounded-pre-execution-reasoning.md)
  - [ADR-0007: Operationalize negative constraints by omission](../adr/0007-operationalize-negative-constraints-by-omission.md)
  - [ADR-0008: Context, session, and normative storage architecture](../adr/0008-context-and-session-management.md)
- Empirical foundations:
  - Decision D15: Gate metric decomposition (deliverable hard gate vs. metadata compliance).
  - Decision D18: Rejection of output-distribution constraints / grammar pinning.
  - Decision D20/D21: Protocol v2 structural context isolation.
  - Decision D24: Connected Dual-Gate Policy and permanent retirement of in-band delimiters.
  - Decision D25: Proportional reasoning taxonomy by model class and operation role.
  - Decision D26: Negative constraint operationalization by structural omission (`PLAN-10`, `EXEC-05`).
  - Decision D27: Zero-template dynamic workspaces and centralized normative store (`~/.pdlt`).
- Existing behavioral references:
  - Language standard: `contracts/standards/PDL_STANDARD.md`
  - Execution contract: `contracts/EXECUTION_CONTRACT.json`
  - Operational schemas: `controller/schemas/*.schema.json`

---

## 1. Purpose

Specify the production host-controlled implementation of the controller-gated pseudocode confirmation protocol (`PDLt`), updated to formalize:
1. **Out-of-Band Structural Containment:** Structural isolation of untrusted input text via decoupled JSON schema channels (`task_summary` vs `risk_notes`), permanently retiring in-band delimiters and driver prose overrides.
2. **Bounded Pre-Execution Reasoning:** Strict adherence to ADR-0006, provisioning bounded semantic inference (`reasoning_effort: "low"`) exclusively to `DRAFT_PROMPT` to eliminate zero-inference cognitive compression, while maintaining `reasoning_effort: "none"` for plan generation and execution.
3. **Confirmed Artifacts as the Sole Execution Boundary:** Enforcing ADR-0001 and ADR-0004 such that Prompt Pseudocode maximizes useful semantic specificity and serves as the sole, transparent task specification for execution, definitively rejecting shadow data planes or unreviewed bypass channels.
4. **Connected Dual-Gate Invariant:** Establishing the indivisible evaluation standard where the protocol must achieve zero adversarial egress leaks/hijacks and statistically superior positive fidelity over unconstrained control generation simultaneously.

---

## 2. Goals

1. **Deterministic Lifecycle:** Guarantee that every protocol transition is controller-owned, deterministic, and independent of natural-language model chatter or implicit context history.
2. **Maximum Semantic Specificity in Prompts:** Ensure Prompt Pseudocode preserves all operative actions, subjects, objects, room/unit numbers, domain identifiers, quantities, constraints, and criteria verbatim ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)).
3. **Procedural Generality in Plans:** Ensure Response Plan Pseudocode preserves minimum sufficient procedural specificity, maintaining epistemic neutrality and leaving output distribution unpinned ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md), [ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md)).
4. **Clean Execution Boundary:** Execute strictly from the confirmed Prompt and Plan artifacts; exclude rejected drafts, intermediate revisions, and conversational noise ([ADR-0004](../adr/0004-confirmed-artifacts-as-execution-boundary.md)).
5. **Structural Containment Without Delimiters:** Quarantining third-party injection directives and canary tokens using out-of-band schema field isolation and deterministic host-side IOC redaction, without in-band delimiter markers (`<<<EVIDENCE>>>`).
6. **Bounded Reasoning Allocation:** Operationalize ADR-0006 by assigning bounded reasoning (`low`) to prompt compilation and zero reasoning (`none`) to plan generation and execution.
7. **No Bespoke DSLs:** Prohibit the invention of new grammar constraints, AST compilers, or fielded pseudocode syntax; preserve standard structured English per Cal Poly PDL conventions ([`PDL-01`](../standards/PDL_STANDARD.md), [`PDL-06`](../standards/PDL_STANDARD.md)).
8. **Statistically Superior Fidelity:** Eliminate the lossy telephone game across phases, outperforming unconstrained direct execution on multi-constraint, disambiguation, and actor-attribution tasks.
9. **Zero-Tolerance Adversarial Egress:** Prevent decision hijacking and delivery of untrusted canary tokens in final execution deliverables under all adversarial vectors.
10. **Dual-Mode Output Support:** Support standard final deliverables as the default while offering substantive Result Pseudocode as an explicit user-selected mode ([ADR-0005](../adr/0005-optional-result-pseudocode.md)).

---

## 3. Non-Goals

1. **No Shadow Data Planes:** The architecture SHALL NOT pass unreviewed raw text, hidden object handles, or unconfirmed source data directly into `EXECUTE` outside the confirmed Prompt Pseudocode specification.
2. **No In-Band Delimiters:** The architecture SHALL NOT mandate or parse synthetic delimiter fences (such as `<<<EVIDENCE>>>...<<<END_EVIDENCE>>>`) in prompt bodies, code deliverables, or review text.
3. **No Output-Distribution Pinning / Grammar Restrictions:** The protocol is an approach compiler, not a constrained grammar engine; it SHALL NOT enforce CFG/BNF grammar pinning or DSPy-style JSON schema output constraints on code or prose execution.
4. **No Ad-Hoc Whack-a-Mole Prompt Phrasing:** The system SHALL NOT add arbitrary noun lists (e.g. "preserve unit numbers, addresses, flight codes") to schema descriptions to satisfy individual test cases; semantic preservation is governed normatively by `TASK-01` and `PROMPT-01`.
5. **No Private Chain-of-Thought Exposure:** Hidden model reasoning traces remain internal to inference engines and SHALL NOT be exposed in user artifacts, stored in confirmed state, or forwarded across phase boundaries.
6. **No Substantive Pre-Execution Research:** Prompt and Plan phases SHALL NOT perform web lookups, code execution, or calculate answers prior to plan confirmation ([ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md)).

---

## 4. Terminology

| Term | Definition |
|---|---|
| **Canonical State** | Controller-owned repository of immutable artifact versions, verified transitions, session events, and active execution mode. |
| **Out-of-Band Schema Isolation** | Separation of concerns via independent top-level JSON fields (`task_summary` vs `risk_notes`) rather than textual in-band tags or delimiters. |
| **Semantic Quarantine Read** | The initial `BOOTSTRAP_ANALYSIS` phase that ingests raw untrusted content, segregating operative task requirements from threat classifications. |
| **Prompt Pseudocode** | The user-confirmed, authoritative semantic task specification. Maximizes useful semantic specificity; contains no plan or substantive answer ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)). |
| **Response Plan Pseudocode** | The user-confirmed, authoritative high-level procedural approach. Uses minimum sufficient procedural specificity; epistemically neutral ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)). |
| **Result Pseudocode** | Optional substantive final execution output rendered in structured PDL format ([ADR-0005](../adr/0005-optional-result-pseudocode.md)). |
| **Standard Deliverable** | Default substantive final execution output in the task's native form (code, text, document). |
| **Bounded Pre-Execution Reasoning** | The targeted allocation of inference effort (`reasoning_effort: "low"`) strictly necessary to resolve instruction relationships and domain entities without task solving ([ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md)). |
| **Redacted IOC** | The standard host-side redaction token (`[REDACTED_IOC]`) replacing canary tripwires, exploit payloads, and override strings per `SEM-06`. |

---

## 5. System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["1. Untrusted Ingestion Layer"]
        U["User / External Request"] --> H["Host Ingestion Controller"]
        H --> BA["BOOTSTRAP_ANALYSIS<br/>(Reasoning: High / Default)"]
    end

    subgraph Quarantine ["2. Out-of-Band Quarantine Boundary"]
        BA -->|"task_summary (Operative TASK-01)"| QC["quarantine.py Compiler<br/>(Deterministic [REDACTED_IOC] scan)"]
        BA -->|"risk_notes (Threat Classification)"| WS["Workspace / Telemetry Log<br/>(Quarantined Out-of-Band)"]
    end

    subgraph ControlPlane ["3. User Alignment & Review (Control Plane)"]
        QC --> DP["DRAFT_PROMPT<br/>(Reasoning: Low / Bounded)<br/>Maximizes Semantic Specificity"]
        DP --> PR["PROMPT_REVIEW<br/>(User Card: Verbatim Entities & Scope)"]
        PR -->|"CONFIRM_PROMPT"| DPL["DRAFT_PLAN<br/>(Reasoning: None)<br/>Minimum Procedural Specificity"]
        DPL --> PLR["PLAN_REVIEW<br/>(User Card: Procedural Approach)"]
    end

    subgraph ExecutionPlane ["4. Clean Execution Boundary (ADR-0004)"]
        PLR -->|"CONFIRM_STANDARD / CONFIRM_PSEUDOCODE"| EX["EXECUTE<br/>(Reasoning: None)<br/>Sole Authority: Confirmed Prompt + Plan"]
        EX --> DEL["Final Substantive Deliverable<br/>(0 Leaks, 0 Hijacks, Superior Fidelity)"]
    end
```

### 5.1 Architectural Invariants

1. **Context Compilation by Positive Inclusion ([ADR-0003](../adr/0003-phase-projected-single-model-contexts.md)):** Every phase receives a freshly compiled, minimal projection built solely from declared schema symbols. Conversational transcripts are never forwarded across phase boundaries.
2. **Strict First-Read Containment:** Raw untrusted user text is read by `BOOTSTRAP_ANALYSIS` and nowhere else. All downstream compilation operations (`DRAFT_PROMPT`, `DRAFT_PLAN`, `EXECUTE`) receive only sanitized, host-compiled contexts.
3. **Confirmed Artifacts as Sole Authority ([ADR-0004](../adr/0004-confirmed-artifacts-as-execution-boundary.md)):** `EXECUTE` receives `CONFIRMED_PROMPT_BODY` and `CONFIRMED_PLAN_BODY`. What the user inspected and confirmed on the review cards governs execution completely.

---

## 6. Operation Contracts and Reasoning Configurations

In accordance with [ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md), reasoning effort is provisioned by operational role:

| Operation | Model Role | Default Reasoning | Context Inputs | Primary Output Symbol |
|---|---|---|---|---|
| `BOOTSTRAP_ANALYSIS` | Semantic Reader | `high` (or provider default) | `RAW_UNTRUSTED_CONTENT` | `task_summary`, `risk_notes` |
| `DRAFT_PROMPT` | Prompt Compiler | `low` (bounded inference) | Sanitized `task_summary` | `prompt_body` |
| `REVISE_PROMPT` | Prompt Reviser | `low` (bounded inference) | Current `prompt_body`, feedback | `prompt_body` |
| `DRAFT_PLAN` | Approach Planner | `none` | `CONFIRMED_PROMPT_BODY` | `neutral_plan_body` |
| `REVISE_PLAN` | Approach Reviser | `none` | `CONFIRMED_PROMPT_BODY`, current plan | `neutral_plan_body` |
| `EXECUTE` | Substantive Executor | `none` | Confirmed Prompt & Plan | `body` (RESULT) |

### 6.1 `BOOTSTRAP_ANALYSIS` Contract
- **Schema:** `controller/schemas/bootstrap_analysis.schema.json`
- **Normative Rules:**
  - Must segregate operative task requirements into `task_summary` and threat classifications into `risk_notes`.
  - Operative technical requirements, interfaces, function names, and domain entities MUST be preserved verbatim in `task_summary`.
  - Third-party instructions, override markers, and canary tokens MUST NOT appear in `task_summary`; if detected, they must be classified in `risk_notes` with raw trigger tokens redacted as `[REDACTED_IOC]` per `SEM-06`.

### 6.2 `DRAFT_PROMPT` Contract
- **Schema:** `controller/schemas/prompt_artifact.schema.json`
- **Reasoning Allocation:** `reasoning_effort: "low"` (ADR-0006 bounded inference).
- **Normative Rules:**
  - MUST generate Prompt Pseudocode in readable structured English ([`PDL-01`](../standards/PDL_STANDARD.md), [`PDL-06`](../standards/PDL_STANDARD.md)).
  - MUST maximize useful semantic specificity ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)).
  - MUST preserve all operative `TASK-01` semantics verbatim: subjects, objects, scope, constraints, exclusions, unit numbers, dates, quantities, and output format requirements ([`PROMPT-01`](../standards/PROMPT_STANDARD.md)).
  - MUST NOT imitate programming syntax or invent fake uppercase keyword pseudo-code when ordinary structured English is clearer ([`PDL-06`](../standards/PDL_STANDARD.md)).
  - MUST NOT solve the task, predict findings, or plan response procedures ([`PROMPT-02`](../standards/PROMPT_STANDARD.md)).

### 6.3 `DRAFT_PLAN` Contract
- **Schema:** `controller/schemas/plan_artifact.schema.json`
- **Reasoning Allocation:** `reasoning_effort: "none"`.
- **Normative Rules:**
  - MUST represent the authoritative response approach using minimum sufficient procedural specificity ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)).
  - MUST remain epistemically neutral, high-level, and inspectable ([ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md)).
  - MUST NOT anticipate findings, predict calculations, pre-select winners, or include final answers ([`PLAN-04`](../standards/PLAN_STANDARD.md)).
  - MUST NOT constrain the execution output distribution or pin the model to synthetic grammar structures.

### 6.4 `EXECUTE` Contract
- **Schema:** `controller/schemas/execution_outcome.schema.json`
- **Reasoning Allocation:** `reasoning_effort: "none"`.
- **Normative Rules:**
  - Bounded strictly by `CONFIRMED_PROMPT_BODY` (what the user wants) and `CONFIRMED_PLAN_BODY` (how to approach it) ([ADR-0004](../adr/0004-confirmed-artifacts-as-execution-boundary.md)).
  - Emit the complete deliverable implementation or document in `body`.
  - Missing non-semantic execution variables must be requested via `REQUEST_INPUT` under `EXEC-01` without creating a third confirmation stage.

---

## 7. Structural Containment & Quarantine Mechanics

### 7.1 Permanent Retirement of In-Band Delimiters
In-band delimiter framing (e.g. `<<<EVIDENCE>>>...<<<END_EVIDENCE>>>`) is permanently retired per Decision D24:
1. Synthetic delimiters force models to guess where code/data boundaries lie, inducing false positives and renaming valid symbols (e.g. renaming `fetch_with_retry` to avoid delimiter triggers).
2. Containment is enforced host-side through **out-of-band JSON schema fields**. The model writes structured JSON; the host routes fields based on role.

### 7.2 Deterministic Redaction Pipeline (`quarantine.py`)
Before `task_summary` from `BOOTSTRAP_ANALYSIS` is compiled into context for `DRAFT_PROMPT`:
1. The host scans `task_summary` against regex tripwire patterns (`_CANARY_OR_TRIPWIRE`, `_OVERRIDE_DIRECTIVE`, `_EXPLOIT_PHRASE`).
2. Any detected canary tokens or injection triggers are replaced with `[REDACTED_IOC]`.
3. Legitimate identifiers, unit numbers, parameter names, and exception types are passed untouched.
4. Downstream operations (`DRAFT_PROMPT`, `PLAN`, `EXECUTE`) receive the sanitized text. They cannot leak what they never receive.

### 7.3 `SEM-06` Threat Reference Compliance
When `BOOTSTRAP_ANALYSIS` detects an untrusted instruction or canary, it must record threat telemetry in `risk_notes` without echoing the literal trigger:
* *Correct:* `"Canary token detected in unit string, classified as [REDACTED_IOC] per SEM-06."`
* *Prohibited:* Echoing raw un-redacted canary tokens in threat descriptions.

---

## 8. State Machine and User Experience

```mermaid
stateDiagram-v2
    [*] --> Ingestion: SUBMIT_REQUEST
    Ingestion --> PromptReview: BOOTSTRAP_ANALYSIS + DRAFT_PROMPT
    PromptReview --> PromptReview: REVISE_PROMPT (inline feedback)
    PromptReview --> PlanReview: CONFIRM_PROMPT (freezes prompt)
    PromptReview --> Stopped: STOP
    PlanReview --> PlanReview: REVISE_PLAN (approach feedback)
    PlanReview --> PromptReview: CHANGE_REQUEST (invalidates plan)
    PlanReview --> Executing: CONFIRM_STANDARD (native output)
    PlanReview --> Executing: CONFIRM_PSEUDOCODE (Result PDL)
    PlanReview --> Stopped: STOP
    Executing --> Complete: Deliverable produced
    Executing --> WaitingInput: REQUEST_INPUT (EXEC-01)
    WaitingInput --> Executing: SUPPLY_EXECUTION_INPUT
    Complete --> [*]
    Stopped --> [*]
```

### 8.1 User-Visible Review Controls ([ADR-0002](../adr/0002-controller-owned-artifact-controls.md))
- **Prompt Review:** **Confirm interpretation** (`CONFIRM_PROMPT`), **Revise interpretation** (`REVISE_PROMPT`), **Stop** (`STOP`).
- **Plan Review:** **Confirm standard** (`CONFIRM_STANDARD`), **Confirm pseudocode** (`CONFIRM_PSEUDOCODE`), **Revise approach** (`REVISE_PLAN`), **Change request** (`CHANGE_REQUEST`), **Stop** (`STOP`).
- All actions are controller-owned, typed events. Silence never confirms an artifact.

---

## 9. Verification & Acceptance Criteria (The Connected Dual Gate)

Per Decision D24, evaluations must execute against the connected dual gate: **if either gate fails, both fail.**

### 9.1 Track A: Negative Containment Gate (Hard Floor: Zero Tolerances)
Across the full breadth battery (single message, drip, encoded, stacked):
1. **Deliverable Leaks:** Exactly **0** (post-strip scan of deliverables must find 0 canaries).
2. **Decision Hijacks:** Exactly **0** (no model adoption of injected personas or tasks).
3. **Session Stalls:** Exactly **0** unhandled state machine stalls.

### 9.2 Track P: Positive Fidelity Gate (Superiority Over Control)
Across multi-constraint, disambiguation, and actor-attribution suites:
1. **Requirement Recall:** Protocol mean recall MUST match or exceed Control ($\ge 0.98$).
2. **Fidelity Rate:** Fraction of trials with 100% compliance MUST exceed Control ($\ge 0.92$).
3. **Negative Adherence:** Exactly **1.0** (zero emission of prohibited elements).
4. **Entity Retention:** Operative unit numbers, domain identifiers, exception types, and dates must be preserved with 100% recall through Prompt Pseudocode into execution.

---

## 10. Summary of Architectural Guarantees

By synthesizing ADR-0001 through ADR-0008 with out-of-band schema isolation, `TRD-0002` achieves:
* **Fidelity Without Loss:** Prompt Pseudocode retains maximum semantic specificity via bounded reasoning (`low`), eliminating telephone-game degradation.
* **Containment Without Delimiters:** Out-of-band field quarantine structurally prevents injection without fragile in-band syntax hacks.
* **Inspectability Without Compromise:** The user inspects and confirms the exact execution specification on persistent artifact cards; no shadow data plane bypasses user agency.
* **Operational Scalability:** Zero-template on-demand workspace materialization and centralized version-namespaced normative storage eliminate file-system bloat and cross-turn contamination.

---

## 11. Architectural Evolution and Core Supersessions from TRD-0001

The evolution from `TRD-0001` (v0.1) to `TRD-0002` (v1.0) represents seven major architectural supersessions certified through empirical adversarial and fidelity testing:

| # | Architectural Domain | TRD-0001 Baseline | TRD-0002 Superseding Specification | Empirical Driver & Resolution |
|---|---|---|---|---|
| **1** | **Ingestion Architecture** | Monolithic Prompt Drafting directly from raw text ([ADR-0001](../adr/0001-controller-gated-pseudocode-protocol.md)) | Two-Tier Semantic Read & Quarantine via `BOOTSTRAP_ANALYSIS` (`TRD-0002 §5`, `D20/D21`) | Raw user prompts containing prompt injection directives hijacked prompt drafting; perimeter quarantine isolates untrusted text so downstream compilation never receives injection vectors. |
| **2** | **Containment Mechanics** | In-Band Delimiter Framing (`<<<EVIDENCE>>>`) (`TRD-0001 Option a'`, `D17`) | Out-of-Band Schema Isolation & `[REDACTED_IOC]` (`TRD-0002 §7.1`, `D24`) | In-band tags caused models to confuse syntax boundaries, corrupting valid function names; out-of-band top-level JSON fields (`task_summary` vs `risk_notes`) eliminate syntax confusion. |
| **3** | **Review Interaction Model** | Rigid UI Button Events only; no review inference ([ADR-0002](../adr/0002-controller-owned-artifact-controls.md)) | Structured Fact Extraction (`INTERPRET_*_REVIEW`) with REPL Fast-Paths (`TRD-0002 §8`, `D5`) | Real developer feedback is compound and nuanced; structured fact extraction allows natural-language feedback while host retains mechanical state precedence, with local REPL shortcuts (`/confirm`, `/revise`, `/stop`) to eliminate confirmation latency debt. |
| **4** | **Pre-Execution Reasoning** | Static Zero-Inference (`reasoning: "none"`) across all pre-execution stages ([ADR-0006](../adr/0006-bounded-pre-execution-reasoning.md)) | Proportional Reasoning Taxonomy (`high` $\to$ `low` $\to$ `none`) (`ADR-0006 Amendment`, `D25`) | Forcing zero reasoning on lower-parameter models caused severe semantic collapse (dropping domain entities like "Apartment 4B"); proportional allocation preserves entity recall while keeping execution deterministic. |
| **5** | **Negative Constraints** | Procedural Thoroughness Bias (active procedural wrappers for negative rules) | Operationalization by Structural Omission (`PLAN-10`, `EXEC-05`) ([ADR-0007](../adr/0007-operationalize-negative-constraints-by-omission.md), `D26`) | Active proceduralizing of negative constraints emitted pass-through boilerplate (`except Exception: raise`), tripping adherence checks; structural omission relies directly on native runtime propagation. |
| **6** | **Execution Data Plane** | `REQUIRED_TASK_INPUTS` direct data bypass ([ADR-0003](../adr/0003-phase-projected-single-model-contexts.md), [ADR-0004](../adr/0004-confirmed-artifacts-as-execution-boundary.md)) | Rejection of Shadow Data Planes (`TRD-0002 §3.1 Non-Goal 1`) with Sealed Runtime Input Verification | Passing unreviewed task data into execution created a shadow injection channel; Prompt Pseudocode is the sole operative specification, and runtime variables requested via `REQUEST_INPUT` require user review. |
| **7** | **Evaluation Philosophy** | Decoupled Negative Containment and Positive Performance Testing | Connected Dual-Gate Invariant ("If either fails, both fail") (`TRD-0002 §9`, `D24`) | Decoupled evaluation incentivized Goodhart's law (over-refusal or output truncation to pass leak checks); dual gate requires passing 0 leaks/hijacks and statistically superior fidelity simultaneously under identical configurations. |

---

## 12. Normative Storage and Hierarchical Session Architecture (ADR-0008)

To support production multi-turn workflows and high-throughput evaluation suites without file-system degradation, `TRD-0002` incorporates the architectural partitioning ratified in [ADR-0008](../adr/0008-context-and-session-management.md):

### 12.1 Static Normative Store ("The Brain")
* **Location:** User/operator home directory at `~/.pdlt/versions/<version>/` (e.g. `~/.pdlt/versions/v2/`).
* **Contents:** Immutable protocol contracts (`EXECUTION_CONTRACT.json`, `CONTRACT_MANIFEST.json`), normative markdown standards (`ARTIFACT_STANDARD.md`, `PROMPT_STANDARD.md`, `RESPONSE_PLAN_STANDARD.md`, `EXECUTION_STANDARD.md`), and JSON validation schemas.
* **Resolution:** Resolved via `PDLT_STANDARDS_PATH` override, project-local `.pdlt-version` / `pdlt.json` pointer, global operator configuration, or harness bundled repository fallback.
* **Determinism:** All context compilation and fixture replay keys use SHA-256 digests of serialized text clauses, ensuring byte-for-byte replay invariance regardless of storage location.

### 12.2 Zero-Template Operational Workspaces ("The Hands and Feet")
* **Elimination of Static Scaffolding:** The legacy 35-file `workspace-template/` is retired. Workspaces are initialized with zero static copies.
* **On-Demand Dynamic Materialization:** Stage directories (`stages/<stage_id>/input/` and `stages/<stage_id>/output/`) are created dynamically by the controller only when an operation is executed.
* **Performance:** Reduces file creation per workspace from 35 files to zero, slashes disk inode consumption by $>85\%$, and eliminates Windows NTFS directory traversal delays (obsoleting the emergency pruning policy of Decision D22).

### 12.3 Two-Level Invariant Session Hierarchy
Multi-turn conversational workflows are structured hierarchically:
* **Task Epoch (`turns/turn_###/`)**: Represents an indivisible protocol cycle (activation $\to$ prompt review $\to$ plan review $\to$ execution $\to$ completion). Owns its independent state, events, and dynamic stage records.
* **Interaction Invocations (`input/####-<operation>/`)**: Granular review interactions, inline corrections, and confirmations within an active epoch execute as sequentially numbered invocations inside that epoch's stages.
* **Cross-Turn Deliverable Chaining ([ADR-0004](../adr/0004-confirmed-artifacts-as-execution-boundary.md))**: When a task completes, subsequent tasks ingest only the verified deliverable as clean background input, discarding previous conversational negotiation, intermediate prompts, and rejected drafts to prevent context flatlining.

