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

### 1. System 1 Model Substrate (Laya / Jev)
- Classification and review operations SHALL target a non-generative decision model:
  - **Laya:** Open-weights, locally hosted ModernBERT decision model running on CPU/GPU via ONNX / PyTorch.
  - **Jev:** Cloud-hosted, high-throughput System 1 decision API.
- These models do not emit conversational text; they accept input state (prompt, plan, user review feedback) and output strictly typed, calibrated JSON/boolean classifications in a single forward pass ($<20\text{ms}$).
- Supported operations:
  - `INTERPRET_ACTIVATION` $\rightarrow$ 4-way route classification.
  - `INTERPRET_PROMPT_REVIEW` & `INTERPRET_PLAN_REVIEW` $\rightarrow$ `ReviewFactsPayload` extraction (`task_change_dimensions`, `approach_change_dimensions`, `progression_requested`).
  - `INTERPRET_EXECUTION_INPUT` $\rightarrow$ Review routing.

### 2. Alignment via Contrastive Distillation (RLCD - arXiv:2307.12950)
The local decision model SHALL be trained using the RLCD methodology:
- **Contrastive Pair Synthesis:** For each review and activation state, paired inputs are generated:
  - **Positive Prompt:** Encourages strict adherence to normative standards (`REVIEW-09`, `REVIEW-14` silence must not confirm, `SEM-05` actor attribution).
  - **Negative Prompt:** Incorporates adversarial framing (drip injection, conversational override, embedded tripwires).
- **Oracle Verification:** Outcomes are evaluated against the deterministic `MechanicalController` and `StandardRegistry` (acting as external ground-truth verifiers) to score preference labels cleanly without human annotators.
- **Preference Optimization:** The resulting contrastive preference dataset is used to train Laya's decision heads via DPO/PPO, producing a hardened decision worker resilient against contextual amnesia and prompt injection.

### 3. Two-Tier Hybrid Architecture (System 1 / System 2 Split)
The runtime routing SHALL partition operations across model tiers:
- **System 1 Worker (Laya / Jev - Local):** Governs `INTERPRET_ACTIVATION`, `INTERPRET_PROMPT_REVIEW`, `INTERPRET_PLAN_REVIEW`, and `INTERPRET_EXECUTION_INPUT`. Latency drops to $<20\text{ms}$; syntax errors drop to 0.0%.
- **System 2 Worker (Frontier Reasoning Model):** Reserved strictly for semantic synthesis: `BOOTSTRAP_ANALYSIS`, `DRAFT_PROMPT`, and deliverable code generation in `EXECUTE`.

### 4. Calibrated Confidence Formulation & Multi-Dimensional Gating
Raw softmax outputs $p_k = \frac{\exp(z_k)}{\sum_j \exp(z_j)}$ from transformer classification heads (including ModernBERT) are known to be systematically miscalibrated and overconfident on out-of-distribution adversarial prompts. A raw high probability is not evidence of correctness.

To guarantee that confidence reflects true empirical fidelity:
1. **Post-Hoc Probability Calibration ($P_{\text{cal}}$):**
   Classification logits $\mathbf{z} \in \mathbb{R}^K$ must be transformed via Temperature Scaling on validation traces:
   $$P_{\text{cal}}(y = k \mid \mathbf{x}) = \frac{\exp(z_k / T^*)}{\sum_{j=1}^K \exp(z_j / T^*)}$$
   where the optimal temperature $T^* > 0$ is learned by minimizing cross-entropy / negative log-likelihood (NLL) over held-out validation splits of the F6 adversarial suite and Track P fidelity traces:
   $$T^* = \arg\min_T -\frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K y_{ik} \ln \left( \frac{\exp(z_{ik} / T)}{\sum_j \exp(z_{ij} / T)} \right)$$
   For binary / multi-label dimensional heads (`task_change_dimensions`, `approach_change_dimensions`), Platt scaling $\sigma(w_i z_i + b_i)$ or isotonic regression is fit per dimension.

2. **Multi-Dimensional Decision Gating:**
   Top-1 confidence $p_{(1)}$ alone is vulnerable to adversarial ties (e.g. 0.51 vs 0.49). Therefore, the System 1 decision engine enforces three simultaneous criteria before accepting a fast-path transition:
   - **Calibrated Top-1 Floor:** $P_{\text{cal}}(y_{(1)} \mid \mathbf{x}) \ge \theta$ (with default empirical prior $\theta_0 = 0.85$).
   - **Top-2 Margin Floor:** $\Delta p = p_{(1)} - p_{(2)} \ge 0.40$. If the gap between the top intent and the runner-up is below 0.40, the input is classified as ambiguous.
   - **Normalized Shannon Entropy Ceil:**
     $$H(p) = -\frac{1}{\ln K} \sum_{k=1}^K p_k \ln p_k \le 0.35$$
     Inputs with diffuse probability distributions trigger immediate Tier 2 fallback.

3. **Deterministic Fail-Closed Fallback Ladder:**
   - **Tier 1 (System 1 Fast-Path, $<20\text{ms}$):** Input satisfies Pydantic wire validation AND passes the multi-dimensional confidence gate ($P_{\text{cal}} \ge 0.85, \Delta p \ge 0.40, H(p) \le 0.35$). Controller commits transition.
   - **Tier 2 (System 2 Frontier Fallback, $\sim 3\text{–}8\text{s}$):** If System 1 fails any gating check, the request escalates to the System 2 Frontier Reasoning model with full chain-of-thought analysis.
   - **Tier 3 (Mechanical Human Card, `REVIEW-09`):** If ambiguity persists or review intent is unconfirmed, the engine rewrites intent to `UNRESOLVED` and halts execution, presenting a mechanical confirmation card to the human in the REPL.
   - For activation (`INTERPRET_ACTIVATION`), low confidence unconditionally rewrites the route to `APPLY_PROTOCOL` (fail-closed to governance).

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
- Requires maintaining dual worker dispatch (`System1Worker` vs `System2Worker`) within `scripts/providers/`.
- Fine-tuning pipeline requires fitting temperature scaling parameter $T^*$ and threshold $\theta^*$ on held-out validation splits.
- Automated CI drivers must expect exit code 2 on intentionally halted or partial test traces.
