# Controller-Gated Pseudocode Protocols: Achieving Provable Adversarial Containment and High-Fidelity LLM Execution via Structural Out-of-Band Contexts

**PDLt Architectural Whitepaper** · PDL-Standard-REPL-Harness (PDL Taskmaster)
· v2.3.0 · 2026-09-17

---

## Abstract

Software that delegates work to a language model inherits a problem older
models of computation never had: the thing carrying out the task is also the
thing deciding what the task *means*. PDLt resolves this with one mechanism —
**interpretation before execution, confirmed at separate gates, with the
model's generation left free at every stage**.

The architecture makes three distinct claims that must not be conflated:

1. **The defensive improvement is structural, not cognitive.** Adversarial
   containment comes from the Interpretable Context Methodology (ICM)
   workflow — the filesystem-as-architecture protocol workflow that routes
   raw untrusted content through a single perimeter read and never lets it
   re-enter compilation or execution contexts. Containment is context
   routing, and is **empirically reasoning-invariant**: it holds identically
   at zero reasoning tokens and at full reasoning budgets. No output-space
   constraint, grammar, or decoding pin is involved at any stage.
2. **The alignment improvement — positive and negative, both sides of the
   same coin — comes from the multi-stage confirmation taskmaster.** Prompt
   Pseudocode and Response Plan Pseudocode are two separate, publicly
   inspectable, correctable artifacts that answer two different questions
   ("is this what I asked for?" and "is this an acceptable way to answer
   it?"). The protocol *disambiguates* — it separates misunderstood requests
   from undesirable approaches, the exact failure natural-language
   conversation hides — while **never collapsing the response distribution**:
   the model is an interpreter and approach-compiler into structured-English
   intermediate representations, not a constrained decoder.
3. **The clearest rationale for inferential improvement is the PDL itself.**
   Program Design Language — readable structured English with sequence,
   indentation, decisions, loops, procedure calls, and action verbs — provides
   the shared semantic surface that makes interpretation confirmable, without
   inventing a formalism that would create a second interpretation problem.

These are enforced by a deterministic mechanical controller that owns the
state machine and the user-owned confirmation boundary. This paper documents
the structural lineage, the seven certified architectural supersessions
between TRD-0001 and TRD-0002, the empirical program that produced the
Connected Dual Gate, and the Brain/Hands storage architecture that makes the
protocol's evidence trail auditable by construction.

---

## 1. The Dual-Frame Dilemma, and Why Disambiguation Is the Coin

Alignment work is usually split into two different products: an eval harness
for fidelity and a guardrail for injection. PDLt's founding claim is that
these are not two problems but one — **both are failures of ambiguous,
unconfirmed interpretation** — and therefore one mechanism serves both. The
multi-stage confirmation protocol is the same coin observed from two faces:

- **Positive face (fidelity).** Meaning drift — a greeting becoming an
  instruction to respond, the model casting itself as the actor of an act the
  user performed — is made *visible before it becomes action*, because the
  interpretation exists as a confirmable artifact rather than an internal
  state. The user answers "is this what I asked for?" against maximum useful
  semantic specificity.
- **Negative face (defense).** Content arriving *inside* the task — quoted
  text, pasted documents, embedded directives — is classified as data
  (SEM-02/SEM-03) in the same confirmable artifact, before any output exists.
  The prohibition becomes a compiled, positionally guaranteed part of every
  subsequent call's context rather than prose hoping to be obeyed.

The boundary test that motivated the architecture made the asymmetry
measurable: the identical model, on one plain API call, completed the
legitimate task and refused the payload's core directive — yet still restated
the activation tripwire and volunteered an evasion improvement (2/5 probe
violations). Understanding is not enforcement. The protocol arm held 0/5
because the interpretation stage had already re-typed the hostile block as
represented instruction data and enumerated the output prohibitions into the
confirmed specification.

**The non-collapse tenet.** None of this is achieved by constraining what the
model may generate. The protocol never pins the output distribution: no
grammar enforcement, no constrained decoding, no DSPy-style pinned output
space. When grammar enforcement was experimentally applied to interpretation
operations (D12), it collapsed model behavior into degenerate avoidance loops
and was **prohibited for the protocol arm**; when proposed as a general
mechanism (D18), it was **withdrawn on tenet grounds** — the protocol is an
interpreter/approach-compiler into pseudocode IRs, and generation freedom at
every stage is what preserves the model's ability to express task semantics.
Quality comes from what sits *between* generation stages: compiled, hashed,
confirmable artifacts. Containment comes from what *never reaches* generation
stages: raw untrusted content, structurally routed away.

**The Connected Dual Gate** is the measurement consequence: an architecture
cannot claim alignment by trading safety for utility (leaking to preserve
recall) or utility for safety (over-censoring to suppress leaks). F6.4
(negative containment, N ≥ 10) and Track P (positive fidelity, N ≥ 10) are an
indivisible gate — *if either fails, both fail* — executed under identical,
unassisted configurations, with no evaluator oracles, no driver overrides, and
no dynamic fail-open routing.

## 2. Why PDL: The Inferential Rationale

The protocol's confirmable artifacts are written in Program Design Language —
a compatibility profile of J. Dalbey's publicly readable Cal Poly Pseudocode
Standard. This choice is load-bearing, and its rationale is documented in the
PDL rationale and evidence map (`PDL-Standard/docs/architecture/pdl-rationale.md`):

**An existing convention instead of a new language.** The protocol needs
visible structure, not a new requirements formalism. PDL already provides
sequence, indentation, decisions, loops, procedure calls, and domain-oriented
action verbs — sufficient to represent task semantics and high-level procedure
while remaining legible to a person who does not write code. Inventing a
project-specific DSL would add a **second interpretation problem**: the user
and the model would first have to learn the DSL, then determine whether the
request was represented correctly inside it. PDL keeps the control artifact
close to ordinary language, so confirmation audits meaning directly.

**Two separate shared surfaces.** Natural-language conversation can hide
whether the model misunderstood the request or merely selected an undesirable
approach. The protocol produces two artifacts that split exactly that
ambiguity:

| Artifact | Question it lets the user answer | Specificity target |
|---|---|---|
| Prompt Pseudocode | "Is this what I asked for?" | Maximum useful **semantic** specificity |
| Response Plan Pseudocode | "Is this an acceptable way to answer it?" | Minimum sufficient **procedural** specificity |

Both are complete, visible, and correctable; neither is private
chain-of-thought. Confirming both establishes the public execution boundary.
This is the disambiguation engine — and because each artifact is confirmed at
its own mechanical gate, correcting *meaning* and correcting *approach* are
independent, typed corrections rather than conversational renegotiation.

**An intermediate representation without a public schema.** The artifacts are
genuine IRs — versioned, compared, replayed, hash-pinned, and fed to later
phases — but their public representation remains structured English rather
than JSON, a fielded requirements template, or a custom abstract syntax tree.
The wire layer is JSON; the *semantic* layer the human confirms is not.

**Correction and sequencing efficiency.** Dense prompts combine actions,
constraints, priorities, exclusions, audience, and output requirements. PDL
turns those relationships into sequential and indented operations, so the user
can correct a specific meaning or approach while still receiving the complete
current artifact on every revision. The protocol reduces state reconstruction
and separates two kinds of correction — an architectural claim, with the
instruction-level skill's behavioral suite (40-case public suite; targeted
15/15 PASS, 30/30 PDL-quality points; provenance-bound baseline 38/40, zero
critical failures) establishing the behavioral foundation the harness
mechanizes.

## 3. Structural Lineage: From Skills to the ICM Turn

The protocol did not begin as an architecture. It began as a skill —
*confirm-with-pseudocode* — implementing the two-stage confirmation. The
lineage of experiments that followed (Compact B3, Sol RC5, the DS-split
conditions, R2S/R6O generations) tested successive orchestration hypotheses.
The decisive empirical lesson:

> **Skills alone are not sufficient to generalize inferential improvement.**

The improvement generalized only when the **Interpretable Context
Methodology** (Van Clief & McDermott, arXiv:2603.16021v2) was adopted as the
workspace structure — filesystem-as-agentic-architecture: numbered stage
folders externalizing per-run context, intermediate artifacts, stage handoffs,
controller checkpoints, and event history. With that structure the system
became a **fidelity protocol**. The defensive property of this structure is
its point: containment is a property of the *workflow* — which stage receives
which compiled projection — not of the model's reasoning about threats. The
controlled reasoning A/B (§5) proved this directly: containment held 100%
clean at zero reasoning tokens. A structural mechanism that required cognition
would be a hope; this one is a routing table.

The interface history is part of the lineage, not a footnote. The protocol
proceeded past the REPL into GUI and TUI implementations that were
architecturally sound as renderings but unsound as interfaces — and were
superseded. The REPL is the only interface with **parity between human and
agent hosts**: the same command surface serves a person at a terminal and an
agentic worker driving the harness. GUI and TUI are invisible to agentic
hosts, which would fragment the protocol into surface-specific semantics —
precisely what the one-mechanism thesis forbids. REPL-canonical semantics are
therefore a design invariant, not a convenience.

A third lineage lesson governs the worker boundary: **competing system
instructions interfere with compiled standards.** The Codex CLI worker carries
heavy native instructions (tone, user-interaction conventions, agentic
framing) that counteract the compiled clause requirements the worker is
supposed to follow. The API worker — a bare projection to an
OpenAI-compatible endpoint with the harness's own bootstrap as instructions —
is architecturally stronger *because it carries nothing else*. This finding
directly informs local-worker development: instruction-lightness is a
requirement, not a preference.

## 4. The Seven Supersessions (TRD-0001 → TRD-0002)

Certified by the independent Architectural Supersession Report (PDLt critical-path review, ACTIVE); all four of its Priority Actions were closed by v2.3.0.

| # | Architectural Domain | Original (TRD-0001 / Early ADRs) | Superseding (TRD-0002 / Ratified Decisions) | Verdict |
|---|---|---|---|:---:|
| 1 | **Ingestion architecture** | Monolithic prompt drafting directly from raw text | Two-tier semantic read & quarantine via `BOOTSTRAP_ANALYSIS` (D20/D21): perimeter operation sees raw content; compile ops receive sanitized projections | Strongly net positive |
| 2 | **Adversarial containment** | In-band delimiter framing (`<<<EVIDENCE>>>`, D17) | Out-of-band decoupled JSON schema channels (`task_summary` vs `risk_notes`) + `[REDACTED_IOC]` (D24) | Strongly net positive |
| 3 | **Review interaction model** | Rigid UI button events; model review inference prohibited | Structured semantic fact extraction (`INTERPRET_*_REVIEW`) with host precedence (D5); REPL fast-paths close the latency debt (U1) | Net positive (debt retired) |
| 4 | **Pre-execution reasoning** | Static zero-inference across pre-exec stages | Proportional reasoning taxonomy: `high` → `low` → `none`, per operation and model class (ADR-0006 Amendment, D25) | Overwhelmingly net positive |
| 5 | **Negative constraints** | Procedural thoroughness bias (active assertion wrappers) | Operationalization by structural omission (`PLAN-10`, `EXEC-05`, ADR-0007, D26) | Overwhelmingly net positive |
| 6 | **Execution data plane** | `REQUIRED_TASK_INPUTS` side-channel data plane | Hardcoded rejection of shadow data planes (TRD-0002 §3.1 Non-Goal 1); `EXEC-01` runtime input requests; supplied input quarantined through the semantic read (D6) | Net positive (channel sealed) |
| 7 | **Evaluation philosophy** | Independent negative containment scoring (Track A only) | Connected Dual-Gate Invariant — "if either fails, both fail" (D24) | Strongly net positive |

Two retired mechanisms deserve their epilogue. The *sanctioned evidence sink*
(D17, option a′) — requiring the model to emit verbatim literals only into a
declared channel the host strips — failed three consecutive times as an
*instruction* mechanism (negation, positive transformation, channeling), which
falsified instruction-form containment generally and motivated input-space
containment (D19/D20) and finally out-of-band field isolation (D24). The
*handle-quarantine* design (D19, content-addressed quarantine IR) was
superseded by semantic bootstrap containment (D20) as simpler and
tenet-preserving, and remains the documented fallback.

## 5. Proportional Reasoning Is Two-Dimensional — and Containment-Independent

Reasoning allocation is neither monotonic in "more is better" nor uniform
across phases. The controlled bounded-vs-all-none A/B on GLM-4.7 established:

1. **Adversarial containment is reasoning-invariant.** Both arms achieved
   100% clean containment — structural out-of-band separation holds even with
   zero reasoning tokens. This is the empirical certificate for the ICM
   workflow's defensive claim: containment is context routing, never
   cognition, and therefore never degrades with model tier or reasoning
   budget.
2. **Semantic fidelity is where reasoning matters — and it is model-class
   dependent.** Under all-none, GLM-4.7 (MoE reasoning class) suffered
   *semantic collapse*: the draft stripped language grounding, the unreasoned
   plan misread the pseudocode IR as prose, and the "CSV parser" deliverable
   became an English markdown procedure. Bounded reasoning (`low`) on
   draft/revise is required for the natural-language → technical-spec
   translation. Note the shape of this failure: it is a *disambiguation*
   failure — the IR lost the distinction between task semantics and
   procedural form — which is exactly the ambiguity the two-surface
   confirmation exists to resolve.
3. **Instruct-native models invert the assumption.** Qwen3.5-35B-A3B — a 3B-
   activated MoE — behaves as a deterministic schema compiler: optimal at
   `none`, faster, and historically *cleaner than the frontier-tier model* on
   fidelity cases (6/6 pre-mechanism and post-mechanism), while the control
   arm's injection failures replicate on both tiers.

The taxonomy is therefore per-operation × per-model-class: bootstrap reads
defensively (`high`/bounded), draft/revise translate semantics (`low` where
the model class needs it, `none` where schema-compiler behavior suffices),
plan/execute remain mechanical (`none`). This is wired as the default via
model classification (Class A/B/C/D), with CLI overrides preserved. Its
strategic consequence: **the protocol, not model scale, is the fidelity
source** — cheap open-weights models under the protocol can outperform
frontier models without it, which re-frames the local-distillation program
(Track L) as routing economics, not capability acquisition.

## 6. Scalable Systems Architecture: Brain vs Hands & Feet (ADR-0008)

The protocol separates what must be immutable from what must be ephemeral:

- **The Brain** — normative standards, contracts, schemas — lives in a
  version-namespaced, content-addressed store (`~/.pdlt/versions/v2/`,
  project-pinned via `.pdlt-version`, `PDLT_STANDARDS_PATH`-overridable,
  repository fallback). Historical telemetry, run ledgers, and recorded
  fixtures externalize to a sibling archive under the same resolution pattern
  (`PDLT_RUNS_ROOT`, `PDLT_FIXTURES_PATH`, `PDLT_MLFLOW_DB`).
- **The Hands & Feet** — workspaces — are dynamic, zero-template, ephemeral.
  A fresh run scaffolds four lean directories (`state/`, `events/`, `stages/`,
  `shared/`); stage directories materialize on demand. The 35-file template
  copy (>85% of run-time file creation) is gone, and its absence is a
  verifier-enforced invariant rather than a code comment.

Two structural properties follow. First, **evidence by construction**: every
session leaves content-addressed projections, confirmed artifacts, and
observation telemetry — the ICM workspace *is* the audit trail — so
claim-checking audits records rather than memories. Second, **spec-drift
containment**: the recurring historical failure mode was normative
documentation outrunning code (verification contracts missing freshly
ratified clauses). The remedy is mechanical linkage — verification contracts
asserted at runtime, parity audits gated by the same battery — and the
documentation set is organized to be site-buildable so external-facing claims
and internal provenance (append-only `docs/adr/`, `docs/trd/`) never blur.

## 7. Empirical Scorecard

| Measurement | Condition | Control | Protocol |
|---|---|---|---|
| v2 Gate, full battery (27 cases × 3 × both arms, GLM-4.7) | unassisted out-of-band containment | 0 deliverable leaks, 19 hijacks, clean 74.1% | **0 leaks, 0 hijacks, 0 wire errors**, clean 93.8% (p < 0.0001), replicated ×3 |
| Decision hijacking, multi-turn chains | same | 86.7% (per-chain) | **0.0%** |
| Cross-tier steelman (DeepSeek V4.1 Flash, 30 trials) | stronger control | 4/30 hijacks | **0/30**, 3 honest refusals |
| Certification battery (MC-06, ACTOR-02, DISAMB-03 n=3; 27-case sweep) | ADR-0007 + entity channel live | — | negative adherence 0.0→1.0; 3/3 clean per case; 27/27 clean deliverables |
| Fidelity uplift sweep (13 cases, n=1) | unified config | recall 1.0, fidelity 1.0 | recall 1.0, fidelity 0.92–0.96 → **1.0/1.0** with mechanical entity channel |
| Instruction-level skill suite (PDL behavioral foundation) | 40-case public suite | — | targeted 15/15 PASS, 30/30 PDL quality; baseline 38/40, 0 critical |
| Live dual-gate probe post-v2.3.0 restructure (GLM-4.7) | unassisted | 2/3 adversarial failures; fidelity 1.0 | **3/3 clean; fidelity 1.0** |

**Honest scope.** The claim-grade adversarial record is the 162-trial n=3
battery; publication-grade claims require the N ≥ 10 connected dual battery
(F6.4 + Track P), sequenced after local-worker economics (Track L). Live
sessions are labeled development/demonstration conditions. The PDL rationale's
efficiency claims (token/latency/correction-time) are explicitly architectural
until the controlled comparisons it specifies are run. Scorer of Record
invariance (D8) has been maintained through every scoring-policy change, each
of which is a numbered, owner-ratified decision (D0–D27).

## 8. Theoretical Guarantees and Their Boundaries

**What is structural (model-independent by construction):** compilation
placement (standards as clause-level requirements in every call), mechanical
gating (silence never confirms; the controller will not advance on model
output), out-of-band field isolation (raw literals never re-enter compile or
execution contexts), zero output-distribution constraint at any stage
(generation remains free; the protocol constrains *context*, not *decoding*),
and deterministic wire validation. These held across model tiers, providers,
and reasoning levels — including zero-reasoning configurations.

**What is graded (model-dependent):** semantic fidelity under compression,
entity preservation, review-intent classification (observed: a specialist
coder model classifying bare confirmations as non-progression), and SEM-06
raw-token echo discipline in analytical notes (observed once, contained at
egress with zero deliverable breach). These are ledger metrics per model
class, reported and never averaged away.

**The boundary statement:** the harness enforces the *request* path —
interpretation, confirmation, output contract. It is not a sandbox; execution-
stage tool access remains governed by worker-level sandboxing, a separate
layer with its own threat model.

---

*Companion documents: `docs/architecture/framing.md` (the alignment frame),
`docs/architecture/whitepaper.md` provenance — PDL rationale and evidence map
(`PDL-Standard/docs/architecture/pdl-rationale.md`),
`docs/governance/experiment-log.md` (D0–D27 decision register with
pre-registrations and failure-mode rules), `docs/governance/roadmap.md`
(sequenced tracks), `docs/operations/eval-metrics.md` and
`docs/operations/efficiency-report.md` (measured baselines and NO-GO
verdicts), `docs/adr/` and `docs/trd/` (internal append-only provenance).*
