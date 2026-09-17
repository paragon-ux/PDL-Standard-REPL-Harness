# PDLt Documentation Index

Site-ready documentation for the PDL-Standard-REPL-Harness (PDL Taskmaster).

## Architecture

- [The Alignment Frame (framing)](architecture/framing.md) — why the harness
  exists: fidelity and injection defense as one mechanism; the boundary test;
  honest scope.
- [Architectural Whitepaper](architecture/whitepaper.md) — the full arc:
  dual-frame thesis, ICM lineage and REPL-canonical parity, the seven
  supersessions, empirical scorecard, and theoretical guarantees.
- [Protocol v2 — Semantic Bootstrap Containment](architecture/protocol-v2-semantic-bootstrap-spec.md)
- [Protocol v2 — Handle Quarantine (fallback, superseded by semantic bootstrap)](architecture/protocol-v2-handle-quarantine-spec.md)

## Operations

- [Evaluation Metrics](operations/eval-metrics.md) — measured paired baselines
  and call-by-call telemetry.
- [Efficiency Report](operations/efficiency-report.md) — cost/latency levers,
  measured optima, and NO-GO verdicts.

## Governance

- [Roadmap](governance/roadmap.md) — tracks F/P/E/M/L/D/S/U, phases 1–9,
  the Connected Dual Gate, and release sequencing.
- [Experiment Decision Register](governance/experiment-log.md) — D0–D27:
  every ratified decision, falsifiable pre-registration, and failure-mode
  register.

## Internal provenance (excluded from site builds)

`docs/adr/` (ADR-0001–0008) and `docs/trd/` (TRD-0001–0002) are
append-only internal architecture records, gitignored in the published
repository. See `docs/adr/README.md` for the decision index.