# ADR-0020: System 1 Environment-Conditioned Boundary Interception & Immediate Refusal Routing

## Status
Accepted

## Context
In evaluation batteries across negative and impossible prompt categories (such as `PDLt-Test` Category 13: `13-05 out_of_scope_medical`, `13-07 stale_knowledge_cutoff`), generative reasoning models (System 2) frequently fail out-of-scope tasks by attempting to diagnose diseases, prescribe medication, or hallucinate web retrieval steps. 

Investigation into the runtime revealed three root causes:
1. **Instruction Contradiction:** System 2 is explicitly instructed in `api_worker.py`: *"You MUST solve the problem... DO NOT insert negative execution prohibitions."* An instruction-following model penalized for refusing defaults to generating non-compliant deliverables.
2. **Environment Blindness:** Models were never informed that the execution sandbox is completely offline without network or internet access, nor that tasks postdating their knowledge cutoff cannot be fetched.
3. **Automated Gate Rubber-Stamping:** Automated harness review gates routinely emit `/confirm` without validating semantic scope, misleading the model into believing the user authorized the out-of-scope plan.
4. **Classification vs. Deliberation Separation:** Determining whether a task is out-of-scope (e.g. medical, legal, or requiring unavailable external network connectivity) is fundamentally a fast semantic classification problem, not a multi-step generative reasoning task.

The engine contract (`wire_payloads.py`) and session loop (`session_engine.py:801-802`) already define `ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY`, which immediately returns a refusal message and closes the session cleanly without entering the multi-stage pipeline. However, `ActivationRouteRecipe` previously excluded this option and lacked environment-awareness.

## Decision
1. **System 1 Boundary Interception:**
   - Extend `ActivationRouteRecipe` to evaluate `BLOCKED_BY_HIGHER_PRIORITY` as an active classification choice at `INTERPRET_ACTIVATION`.
   - Condition classification criteria on runtime environment variables:
     - `PDLT_SANDBOX_NETWORK` (default `false`): Intercepts tasks requiring outbound HTTP, socket, or live web scraping.
     - `PDLT_POLICY_SCOPE` (default `technical`): Intercepts out-of-scope medical diagnosis/prescriptions and legal counsel.
     - `PDLT_KNOWLEDGE_CUTOFF` (default `2024-06`): Intercepts queries demanding events beyond the cutoff when live search is disabled.
2. **Deterministic Fast-Path Guardrails:**
   - Provide high-confidence pattern classification in `ActivationRouteRecipe` for immediate (<1ms) boundary enforcement.
3. **Wire Conformance & Zero Contract Mutation:**
   - Map `BLOCKED_BY_HIGHER_PRIORITY` directly to `ActivationDecisionPayload(route=ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY, response=...)`.
   - Core protocol contracts (`src/pdl_taskmaster/contracts/`) remain 100% frozen.
4. **Worker Instruction Grounding:**
   - Update worker prompt instructions in `api_worker.py` to declare the sandbox environment as strictly offline, and explicitly clarify that legitimate refusals and infeasibility proofs are permitted.
5. **Decoupling RLCD Optimization:**
   - By offloading boundary enforcement and refusal to System 1 (ModernBERT), System 2 fine-tuning datasets remain 100% positive, eliminating the gradient conflict between helpfulness and safety.

## Consequences
- **Positive:** Out-of-scope medical and network-dependent tasks are intercepted in `<15ms` before any tokens are wasted on prompt drafting or planning.
- **Positive:** False positives (e.g., executing medical prescriptions after automated `/confirm`) are completely eliminated.
- **Positive:** System 2 is liberated from conflicting meta-prohibitions.
- **Neutral:** Test runners must recognize `BLOCKED_BY_HIGHER_PRIORITY` as a passing verdict for prompts whose ground truth oracle mandates refusal.
