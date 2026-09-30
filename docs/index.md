# PDLt Documentation Index

Site-ready documentation for the PDL-Standard-REPL-Harness (PDL Taskmaster).

## Architecture

- [The Alignment Frame (framing)](architecture/framing.md) — why the harness
  exists: fidelity and injection defense as one mechanism; the boundary test;
  honest scope.
- [Architectural Whitepaper](architecture/whitepaper.md) — the full case:
  mechanism, design history, and evidence in public language.
- [Whitepaper — internal edition](architecture/whitepaper-internal.md) — the
  same architecture with ADR/decision-register citations; provenance for the
  public edition.
- [Protocol v2 — Semantic Bootstrap Containment](architecture/protocol-v2-semantic-bootstrap-spec.md)
- [Protocol v2 — Handle Quarantine (fallback, superseded by semantic bootstrap)](architecture/protocol-v2-handle-quarantine-spec.md)

## Operations

- [Prompt Catalogue 105 Benchmark Report](operations/catalogue-105-benchmark-report.md) — 100%
  pass rate scoreboard (105/105), empirical latency decomposition, and optimization roadmap.
- [Empirical Latency & Performance Decomposition](operations/LATENCY_AND_PERFORMANCE_ANALYSIS.md) — call-by-call
  decomposition of all 405 API calls across the 105-prompt run matched to OpenRouter provider logs.
- [Evaluation Metrics](operations/eval-metrics.md) — measured paired baselines
  and call-by-call telemetry.
- [Efficiency Profile](operations/EFFICIENCY.md) — OpenRouter reference stack
  speed, pricing, and empirical latency breakdown.

## Releases

- [v2.6.0 (Release Candidate 1)](releases/v2.6.0.md) — 100% Catalogue Pass Rate (105/105),
  ADR-0018 Pydantic SSOT, ADR-0019 Headless Waiting-Input, ADR-0020 System 1 Refusal Routing,
  and Autonomous Host Sandbox Execution.
- [v2.5.1 (Alpha)](releases/v2.5.1.md) — System 1 (Jev/ModernBERT) baseline routing (ADR-0017),
  Live REPL Session Viewer web UI (`/viewer`), ASCII-safe deliverable cards, and prompt-file ingestion.
- [v2.5.0 (Alpha)](releases/v2.5.0.md) — Substantive correctness verification (ADR-0013),
  OS-native execution sandbox (ADR-0015), Pydantic SSOT (ADR-0016), and REPL Dev Mode.
- [v2.4.0](releases/v2.4.0.md) — Umbrella CLI (`pdlt`), global normative store initialization.
- [v2.3.0](releases/v2.3.0.md) — Version-pinned normative store and multi-tier standards resolution.

## Governance & Integrity
 
- [Anti-Overfitting & Benchmark Integrity Standard](guardrails/ANTI_OVERFITTING_AND_BENCHMARK_INTEGRITY.md) — GUARD-01 to GUARD-05: normative invariants governing protocol non-interference, zero algorithmic injection, and anti-gaming verification.
- [Roadmap](governance/roadmap.md) — tracks F/P/E/M/L/D/S/U, phases 1–12,
  the Connected Dual Gate, and release sequencing.
- [Experiment Decision Register](governance/experiment-log.md) — D0–D29:
  every ratified decision, falsifiable pre-registration, and failure-mode
  register.
- [Regressions Log](governance/regressions_log.md) — human-readable log of verified runtime regressions and normative remediations.
- [Regression Failure Ledger](governance/regressions-log.jsonl) — mechanized
  pre-confirmation regression log linking Session failure modes to contract fixes.

## Architecture & Internal Provenance

`docs/adr/` (ADR-0001–0020) and `docs/trd/` (TRD-0001–0003) are
tracked append-only architecture decision records. See `docs/adr/README.md` for the decision index.