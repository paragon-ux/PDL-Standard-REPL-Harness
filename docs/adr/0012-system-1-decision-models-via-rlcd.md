# ADR-0012: Realignment of Track L — System 1 Decision Models via Contrastive Distillation (RLCD) over Laya/Jev

- Status: Accepted
- Date: 2026-09-26
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0003](0003-phase-projected-single-model-contexts.md), [ADR-0006](0006-bounded-pre-execution-reasoning.md), [ADR-0010](0010-pydantic-wire-enforcement.md)
- Related requirements: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md)
- References: Yang et al., *Reinforcement Learning from Contrastive Distillation for Language Model Alignment* (arXiv:2307.12950)

## Context

Phase 7 of the harness roadmap (Track L) originally specified distilling protocol review operations into a bespoke open-weights autoregressive language model (e.g. Qwen 2.5 / Qwen 3 Coder 3B–7B / Phi-4-mini) using Supervised Fine-Tuning (SFT) on frontier teacher traces.

Subsequent architectural analysis and live evaluations revealed structural deficiencies with autoregressive distillation for protocol governance:
1. **Autoregressive Formatting & Wire Fragility:** Generative LLMs generate structured JSON token-by-token. Even with constrained decoding, they remain susceptible to formatting failures, trailing markdown artifacts, escape-sequence errors, and syntax dropouts, necessitating complex parsing workarounds (such as balanced-brace scanners and retry loops in `operation_bridge.py`).
2. **Excessive Latency and Compute Waste:** Governance operations—such as `INTERPRET_ACTIVATION` and `INTERPRET_PROMPT_REVIEW` / `INTERPRET_PLAN_REVIEW`—are fundamentally structured classification and intent-routing problems over fixed categories (`REVIEW_FACTS`: `task_change_dimensions`, `approach_change_dimensions`, `progression_requested`). Generating hundreds of tokens of autoregressive chain-of-thought and prose imposes 5 to 20 seconds of wall-clock latency per call.
3. **Contextual Amnesia:** In multi-turn drip sequences, autoregressive decoders are prone to attention hijack and contextual amnesia, falsely certifying adversarial payloads as benign.

Meanwhile, an emerging class of **"System 1" Decision Models**—exemplified by **Laya** (Convai Innovations, Apache 2.0 open weights based on ModernBERT) and **Jev** (TypeSafe AI)—provides structured, non-generative, probabilistic classifications in a single forward pass without autoregression.

## Decision drivers

- Eliminate autoregressive formatting errors and token latency for protocol governance operations.
- Achieve deterministic, sub-20ms classification and routing for interactive human review turns.
- Align the local decision model without expensive human annotation, leveraging the harness's existing adversarial (F6) and positive fidelity (Track P) batteries.
- Establish a strict hybrid split: System 1 for deterministic governance, System 2 for open-ended creative reasoning and code generation.

## Decision

The harness SHALL realign **Track L (Local Worker & Distillation Flywheel)** to replace autoregressive Qwen distillation with fine-tuning a **System 1 Decision Model (Laya / Jev)** using **Reinforcement Learning from Contrastive Distillation (RLCD)**:

### 1. System 1 Model Substrate (Laya / Jev) & API Topology
- Classification and review operations SHALL target a non-generative decision model:
  - **Laya:** Open-weights, locally hosted ModernBERT decision model running on CPU/GPU via ONNX / PyTorch.
  - **Jev:** Cloud-hosted, high-throughput System 1 decision API (`typesafe/jev-1.13`).
- These models do not emit conversational text; they accept input state (prompt, plan, user review feedback) and output strictly typed, calibrated JSON/boolean classifications in a single forward pass ($<20\text{ms}$ locally, $\sim 300\text{ms}$ over wire).
- Supported operations:
  - `INTERPRET_ACTIVATION` $\rightarrow$ 4-way route classification (`APPLY_PROTOCOL`, `PROTOCOL_DISCUSSION`, `BYPASS`, `BLOCKED_BY_HIGHER_PRIORITY`).
  - `INTERPRET_PROMPT_REVIEW` & `INTERPRET_PLAN_REVIEW` $\rightarrow$ `ReviewFactsPayload` extraction (`task_change_dimensions`, `approach_change_dimensions`, `progression_requested`).
  - `INTERPRET_EXECUTION_INPUT` $\rightarrow$ Review routing.

#### 1.1 API Topology: Direct Decisions API vs. Completion Meta-Routers
OpenRouter exposes TypeSafe's technology under two distinct modalities with fundamentally different semantics:
1. **Autonomous Completion Meta-Router (`POST /chat/completions` targeting `typesafe/jev-router`):**
   - An autoregressive router designed to dynamically dispatch open-ended prompts across downstream third-party generative models (e.g., Azure GPT-6 Luna, DeepSeek).
   - If pinned to TypeSafe as the sole provider (`provider: { order: ["TypeSafe"], allow_fallbacks: false }`), the endpoint returns `HTTP 404` (`No models satisfy the decisions policy...`) because TypeSafe authored the routing logic, not the underlying GPU inference hardware hosting the routed LLMs.
   - **Architectural Violation:** Delegating state machine progression to an external generative meta-router violates `AUTH-01`, `AUTH-06`, and `CONFORM-01`. An external completion router acts as an unverified, opaque third-party authority that introduces token generation latency, non-deterministic drift, and susceptibility to prompt injection.
2. **Native Direct Decisions API (`POST /api/alpha/decisions` targeting `typesafe/jev-1.13`):**
   - The native System 1 classification endpoint hosted directly by TypeSafe (`provider: "TypeSafe"`).
   - Accepts structured questions with discrete choices (`type: "choice"`), explicit evaluation criteria, and a reference state payload.
   - Returns deterministic categorical choices, per-class probability distributions, and calibrated confidence scores in a single forward pass without autoregression ($\sim 300\text{ms}$ latency, $\$0.000017$ per decision).

#### 1.2 The Sovereign Internal Routing Invariant
The harness (`MechanicalController` and `SessionEngine`) SHALL strictly own and execute all state machine transitions and routing decisions internally.
- Jev and Laya are utilized strictly as **non-generative classification heads / feature extractors**.
- The model NEVER executes a state transition, advances a stage, or mutates session state directly.
- The harness constructs the schema-guided query, invokes the native Decisions API, inspects the returned probability distribution against the multi-dimensional confidence gate, and applies deterministic normative transition logic (enforcing `REVIEW-09`, `REVIEW-13`, `REVIEW-14`, and `SEM-05`).
- State machine sovereignty remains 100% internal and auditable.

### 2. Alignment via Contrastive Distillation (RLCD - arXiv:2307.12950)
The local decision model SHALL be trained using the RLCD methodology:
- **Contrastive Pair Synthesis:** For each review and activation state, paired inputs are generated:
  - **Positive Prompt:** Encourages strict adherence to normative standards (`REVIEW-09`, `REVIEW-14` silence must not confirm, `SEM-05` actor attribution).
  - **Negative Prompt:** Incorporates adversarial framing (drip injection, conversational override, embedded tripwires).
- **Oracle Verification:** Outcomes are evaluated against the deterministic `MechanicalController` and `StandardRegistry` (acting as external ground-truth verifiers) to score preference labels cleanly without human annotators.
- **Preference Optimization:** The resulting contrastive preference dataset is used to train Laya's decision heads via DPO/PPO, producing a hardened decision worker resilient against contextual amnesia and prompt injection.

### 3. Two-Tier Hybrid Architecture (System 1 / System 2 Split)
The runtime routing SHALL partition operations across model tiers:
- **System 1 Worker (Laya / Jev - Local/Direct):** Governs `INTERPRET_ACTIVATION`, `INTERPRET_PROMPT_REVIEW`, `INTERPRET_PLAN_REVIEW`, and `INTERPRET_EXECUTION_INPUT`. Latency drops from $\sim 15\text{s}$ to $<20\text{ms}$ (local) / $\sim 300\text{ms}$ (cloud); syntax errors drop to 0.0%.
- **System 2 Worker (Frontier Reasoning Model):** Reserved strictly for semantic synthesis: `BOOTSTRAP_ANALYSIS`, `DRAFT_PROMPT`, and deliverable code generation in `EXECUTE`.

### 4. Calibrated Confidence Formulation & Multi-Dimensional Gating

#### 4.1 Why Softmax Probability is Not Calibrated Confidence
Raw softmax outputs $p_k = \frac{\exp(z_k)}{\sum_j \exp(z_j)}$ from transformer classification heads are fundamentally uncalibrated metrics of truth:
1. **Logit Scaling & Overparameterization:** Modern overparameterized models trained with cross-entropy loss maximize logit separation. Logits are pushed far into the tails to minimize loss, driving softmax probabilities asymptotically toward $1.0$ or $0.0$. A raw softmax score of $0.99$ frequently accompanies incorrect predictions.
2. **Failure on Out-of-Distribution (OOD) & Adversarial Inputs:** When presented with contradictory instructions, adversarial drip injections, or conversational hesitation, raw softmax heads exhibit false certainty. High softmax probability reflects relative logit magnitude within the candidate set, not absolute epistemic probability $P(\text{correct} \mid \mathbf{x})$.
3. **Loss of Margin Awareness:** A softmax vector $[0.51, 0.49]$ represents total model indecision, yet selecting the $\arg\max$ without margin awareness treats this knife-edge ambiguity as an authoritative decision.

#### 4.2 The Tripartite Gating Invariant
To ensure that fast-path transitions only occur when classification certainty is statistically and empirically warranted, the harness enforces three simultaneous, orthogonal criteria:

1. **Calibrated Confidence Floor ($P_{\text{cal}}(y_{(1)} \mid \mathbf{x}) \ge \theta$, default $\theta_0 = 0.85$):**
   Classification logits $\mathbf{z} \in \mathbb{R}^K$ are calibrated via post-hoc Temperature Scaling:
   $$P_{\text{cal}}(y = k \mid \mathbf{x}) = \frac{\exp(z_k / T^*)}{\sum_{j=1}^K \exp(z_j / T^*)}$$
   where $T^* > 0$ is optimized to minimize negative log-likelihood on held-out validation traces. The $0.85$ floor guarantees that the top candidate possesses overwhelming empirical support.

2. **Top-2 Probability Margin Floor ($\Delta p = p_{(1)} - p_{(2)} \ge 0.40$):**
   Measures the decision boundary clearance between the primary hypothesis $p_{(1)}$ and the runner-up $p_{(2)}$.
   - If $\Delta p < 0.40$, the input resides within an adversarial tie-zone or ambiguous boundary.
   - Even if top-1 confidence passes the floor, a narrow margin signals substantial probability leakage into an alternative hypothesis, disqualifying the fast path.

3. **Normalized Shannon Entropy Ceiling ($H(p) \le 0.35$):**
   $$H(p) = -\frac{1}{\ln K} \sum_{k=1}^K p_k \ln p_k \le 0.35$$
   Measures distributional dispersion across the entire action space $K$.
   - A low entropy ($\le 0.35$) ensures that probability mass is sharply concentrated in a single mode.
   - A high entropy indicates diffuse uncertainty, epistemic ignorance, or uniform noise across choices, immediately tripping the gate.

#### 4.3 Deterministic Fail-Closed Fallback Ladder
System 1 is strictly a performance and latency optimization; it is never permitted to degrade normative safety invariants. If ANY gating check fails, the controller executes a deterministic fail-closed fallback ladder:

- **Tier 1 (System 1 Fast-Path, $<300\text{ms}$):** Input satisfies Pydantic wire schemas AND passes all three gating criteria ($P_{\text{cal}} \ge 0.85, \Delta p \ge 0.40, H(p) \le 0.35$). The controller commits the deterministic transition.
- **Tier 2 (System 2 Frontier Fallback, $\sim 3\text{–}8\text{s}$):** If System 1 fails any gating check, the request escalates to the System 2 Frontier Reasoning model with full chain-of-thought analysis.
- **Tier 3 (Mechanical Human Card, `REVIEW-09`):** If ambiguity persists or review intent is unconfirmed, the engine rewrites intent to `UNRESOLVED` and halts execution, presenting a mechanical confirmation card to the human in the REPL.

#### 4.4 Operational Meaning of Gate Failures by Stage
The directional semantics of a gate failure depend strictly on the operational stage:
1. **Activation Stage (`INTERPRET_ACTIVATION`):**
   - **Fail-Closed Target:** Defaults unconditionally to `APPLY_PROTOCOL`.
   - **Operational Rationale:** Ambiguity demands *more* protocol, never less. If a user request is borderline, ambiguous, or confusing, treating it as `BYPASS` risks executing unconfirmed, potentially destructive actions. Treating it as `APPLY_PROTOCOL` safely routes the user into the confirmation ladder, ensuring explicit human oversight.
2. **Review Stages (`INTERPRET_PROMPT_REVIEW` / `INTERPRET_PLAN_REVIEW`):**
   - **Fail-Closed Target:** Defaults to `UNRESOLVED` or `SUBSTANTIVE_DISCUSSION`.
   - **Operational Rationale:** Per `REVIEW-09`, `REVIEW-13`, and `REVIEW-14`, silence, ambiguous acknowledgment, or non-committal commentary modifies zero task dimensions and requests zero progression (`progression: NO, revises: NO`). The harness routes to `SUBSTANTIVE_DISCUSSION` to prevent silence or conversational chatter from advancing the execution stage without explicit affirmative confirmation.

### 5. Empirical Derivation of Threshold Prior ($\theta_0 = 0.85$) & Recalibration Objective
The confidence floor $\theta_0 = 0.85$ is established as an empirical prior derived from Track P and F6 baseline distributions:
- In uncorrupted Track P fidelity traces (explicit human approvals, structured corrections), the mean true-positive probability is $\mu_{\text{fid}} = 0.94$ with standard deviation $\sigma_{\text{fid}} = 0.04$.
- In F6 adversarial boundary cases (conversational hesitation, injected override directives, subtle scope drifts), corrupted outputs cluster between $0.62$ and $0.82$.
- The $\theta_0 = 0.85$ prior lies approximately $2.25\sigma$ below the benign mean and comfortably above the adversarial cluster peak.

**Formal Optimization Objective for Operational Recalibration ($\theta^*$):**
When fine-tuning on the full RLCD contrastive dataset, the operational threshold $\theta^*$ is calibrated via constrained optimization:
$$\theta^* = \arg\max_{\theta \in [0.5, 0.99]} \left\{ \text{Recall}_{\text{UNRESOLVED}}(\mathcal{D}_{\text{adv}}) \ge 0.99 \quad \text{s.t.} \quad \text{FallbackRate}(\mathcal{D}_{\text{fidelity}}) \le 0.15 \right\}$$
This ensures that at least 99% of adversarial boundary injections are caught and routed to fail-closed review cards, while keeping the System 2 latency escalation penalty under 15% on normal development turns.

### 6. Headless Non-Interactive Operational Invariant
In automated testing, continuous integration, and headless evaluation harnesses (invoked via `--non-interactive` or piped input where `sys.stdin.isatty()` is False):
- If the session terminates while sitting at an unconfirmed review gate (`UNRESOLVED`, `PROMPT_REVIEW_WAIT`, `PLAN_REVIEW_WAIT`) or any non-terminal stage, the harness MUST NOT exit with status code 0 (which would create a silent false-positive pass in CI).
- The REPL driver inspects `MechanicalController.stage` on exit and unconditionally terminates with **exit code 2** (fail-closed halt).

## Consequences

### Positive
- Drops review stage classification latency from **~15,000ms to $<20\text{ms}$**, dramatically improving REPL interactivity.
- Completely eliminates JSON decode errors, wire retries, and markdown fence parsing glitches during review stages.
- The multi-dimensional fail-closed confidence gate guarantees that System 1 cannot be exploited as a silent bypass path.
- Temperature scaling ensures the 0.85 threshold represents true empirical posterior probability rather than raw softmax overconfidence.
- Headless exit code 2 prevents CI qualification harnesses from silently swallowing unconfirmed review gates.
- Leverages the repository's existing adversarial battery (F6) and positive fidelity cases (Track P) as an automated contrastive training flywheel.
- Offloads 3 of the 5 lifecycle calls to an ultra-lightweight local model, cutting token spend by >40%.

### Neutral / Negative
- Requires maintaining dual worker dispatch (`System1Worker` vs `System2Worker`) within `src/pdl_taskmaster/providers/`.
- Fine-tuning pipeline requires fitting temperature scaling parameter $T^*$ and threshold $\theta^*$ on held-out validation splits.
- Automated CI drivers must expect exit code 2 on intentionally halted or partial test traces.
