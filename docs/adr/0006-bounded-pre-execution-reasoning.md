# ADR-0006: Bound pre-execution reasoning and material guessing

- Status: Accepted
- Date: 2026-08-06
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related requirements: [TRD-0001 Sections 10.1 and 10.2](../trd/0001-controller-gated-pseudocode-protocol.md#101-prompt-pseudocode)

## Context

Prompt interpretation and response planning do not require the substantive
reasoning needed to solve the user's task. Allowing full task analysis before
confirmation can leak answers into artifacts, anchor the later execution, and
spend tokens on an interpretation or approach the user may reject.

Eliminating reasoning entirely is also incorrect. Producing faithful
pseudocode requires bounded semantic work, including:

- resolving ordinary references and instruction relationships;
- preserving priorities, exclusions, conditions, and ordering;
- distinguishing a complete interpretation from a response strategy;
- producing valid structured English;
- checking that a plan is inspectable without predicting its result.

Natural language always requires some inference. Requiring clarification for
every possible interpretation would create excessive interruption and defeat
the purpose of the visible correction loop.

## Decision

Prompt and Plan phases SHALL use only the reasoning necessary to create and
validate their respective user-visible artifacts.

Before execution, the model SHALL NOT:

- solve the task;
- research substantive findings;
- calculate requested results;
- select winners or conclusions;
- invent missing requirements;
- silently improve the request;
- fill consequential gaps with speculative assumptions.

Ordinary semantic inference MAY be used when it produces one coherent,
inspectable interpretation without materially adding to the request. The
Prompt Pseudocode SHALL expose the interpretation actually formed so the user
can correct it.

When missing information prevents a coherent artifact or requires choosing
between materially different goals, scopes, output requirements, safety
postures, costs, or irreversible actions, the system SHALL request the smallest
targeted clarification needed. Clarification SHALL not become a general
ambiguity-enumeration DSL.

The controller SHOULD remove reasoning about protocol branching by presenting
explicit events. In particular, Plan review SHOULD distinguish **Revise
approach** from **Change request** rather than asking the model to guess which
kind of change the user intended.

This decision does not limit substantive reasoning during execution. After the
confirmed pair is available, the executor MAY use the reasoning effort required
to satisfy the request safely and correctly while remaining within the
confirmed plan.

## Consequences

### Positive

- Fewer tokens are spent solving rejected interpretations or plans.
- Prompt and Plan artifacts are less likely to contain premature conclusions.
- The user retains control over consequential assumptions.
- Ordinary requests are not interrupted by exhaustive ambiguity analysis.
- Execution reasoning begins from confirmed semantic and procedural boundaries.

### Negative

- The boundary between harmless inference and material guessing still requires
  semantic judgment.
- Excessively weak pre-execution reasoning can omit instruction relationships.
- Excessively aggressive clarification can create interaction fatigue.
- Model reasoning controls are provider-dependent and cannot replace behavioral
  validation.

## Alternatives considered

### Use no reasoning before execution

Rejected. Semantic interpretation, PDL generation, and plan-poisoning detection
cannot be performed reliably without any inference.

### Allow full analysis before confirmation

Rejected. It increases cost and permits findings to anchor or contaminate the
confirmation artifacts.

### Ask about every ambiguity

Rejected. The artifact correction loop is the normal ambiguity-resolution
mechanism; targeted clarification is reserved for materially blocking gaps.

---

## Amendment: Proportional Pre-Execution Reasoning and Model Class Taxonomy

- Status: Ratified (Decision D25 / Milestone)
- Date: 2026-09-16
- Related specifications: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md)

### 1. Context and Problem Statement

Empirical evaluation across disparate model architectures (`z-ai/glm-4.7`, `meta-llama/llama-3.3-70b-instruct`, `qwen/qwen3.5-35b-a3b`) demonstrated that:
1. **Cognitive Density Invariance:** Lower-parameter, quantized, or sparse MoE models exhibit lower cognitive density per token. Forcing `reasoning: none` on models with lower active capacity induces the exact same failure modes observed on GLM-4.7 under zero reasoning (e.g. dropping nested domain entities like "Apartment 4B", defaulting to wrong execution languages, or taking superficial code parsing shortcuts).
2. **Rejection of Static Token-Tier Heuristics:** Provider-independent analysis confirms that static token-to-tier mappings (e.g., claiming "low" effort is strictly 100–300 tokens) are empirical fallacies outside specific proprietary APIs. In live production runs, GLM-4.7 generated 2,123 reasoning tokens under `effort: "low"`, Anthropic enforces a strict 1,024 minimum token budget, and standard instruct models do not support API reasoning parameters.
3. **The Steelman Mandate:** A scientifically rigorous steelman evaluation requires allocating inference-time reasoning compute proportionally to the model class, rather than handicapping lower-parameter or non-thinking architectures with artificial compute starvation.

### 2. Normative Operational Intent

Pre-execution reasoning allocation is defined strictly by **Operational Intent**, invariant across all models:

1. **`BOOTSTRAP_ANALYSIS` (Threat Untangling & Semantic Isolation):** Requires **Defensive Reasoning** (High / unconstrained CoT on thinking models; structured analytical decomposition on instruct models). The model must mentally decouple adversarial injection directives from substantive tasks to strictly populate `task_summary` vs `risk_notes` per SEM-06.
2. **`DRAFT_PROMPT` / `REVISE_PROMPT` (Semantic Specification Compilation):** Requires **Bounded Pre-Execution Reasoning** (Low / proportional CoT). The inference budget is strictly calibrated to the minimum compute needed to guarantee 100% entity preservation (`TASK-01`) without entering substantive problem-solving or algorithmic drift.
3. **`DRAFT_PLAN` / `REVISE_PLAN` / `EXECUTE` (Procedural Compilation & Egress):** Strictly **Zero Reasoning (`"none"`)**. Planning and execution are mechanical, deterministic translations of confirmed artifacts. Reasoning here introduces epistemic drift, non-determinism, and wire conformity violations.

### 3. Model Classification Mapping Matrix

The runtime harness binds concrete reasoning configurations per model capability class (in `runtime/model_classification.py`):

- **Class A: Native Effort-Tier Models (Zhipu GLM-4.7, OpenAI o-series):**
  - `BOOTSTRAP_ANALYSIS`: `reasoning_effort: "high"`
  - `DRAFT_PROMPT` / `REVISE_PROMPT`: `reasoning_effort: "low"`
  - `DRAFT_PLAN` / `REVISE_PLAN` / `EXECUTE`: `reasoning_effort: "none"` (`{"enabled": false}`)
- **Class B: Explicit Token-Budget Models (Anthropic Claude Thinking):**
  - `BOOTSTRAP_ANALYSIS`: `budget_tokens: 4096`
  - `DRAFT_PROMPT` / `REVISE_PROMPT`: `budget_tokens: 1024` (architectural minimum)
  - `DRAFT_PLAN` / `REVISE_PLAN` / `EXECUTE`: thinking disabled
- **Class C: Unbounded Thinking / CoT Open-Weights (DeepSeek R1, Qwen Thinking):**
  - Thinking tags enabled on `BOOTSTRAP` and `DRAFT_PROMPT` bounded by max generation ceilings.
  - Thinking tags disabled on `PLAN` and `EXECUTE`.
- **Class D: Pure Instruct / Quantized Models (Llama 3.3 70B, Qwen 3.5 Instruct):**
  - API reasoning parameter disabled (`reasoning: {enabled: false}`).
  - Deliberative compute provided in-band via structured schema decomposition (`approach_notes` and intermediate semantic fields).


