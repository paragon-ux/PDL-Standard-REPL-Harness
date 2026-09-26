# Changelog

All notable changes to the PDL Taskmaster repository and `pdl-taskmaster` package are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.4.0] - 2026-09-26

Full release documentation: [`docs/releases/v2.4.0.md`](docs/releases/v2.4.0.md)

### Added
- Standard Python package distribution `pdl-taskmaster` on PyPI (`pip install pdl-taskmaster`, `uv add pdl-taskmaster`).
- Unified umbrella CLI `pdlt` supporting `pdlt` (interactive REPL), `pdlt version`, `pdlt init [--global|--local]`, and `pdlt verify`.
- 4-Tier standards precedence resolution in `NormativeStore` (`PDLT_STANDARDS_PATH` $\to$ `./contracts/` $\to$ `~/.pdlt/versions/v2/contracts/` $\to$ bundled package data).
- Strongly typed Pydantic v2 wire enforcement (ADR-0010) across all semantic operations (`wire_payloads.py`), with automated `ValidationError` operator feedback.
- In-memory VFS substrate `MemoryWorkspaceRun` and `MemoryAtomicJsonStore` (ADR-0011) executing turn handoffs in RAM buffers ($<1\text{ms}$ latency).
- Support for non-generative System 1 decision models (ADR-0012) verified with `typesafe/jev-router`.
- Self-contained offline test fixtures vendored in `tests/fixtures/` (~220KB), enabling 100% offline testing.
- GitHub Actions OIDC Trusted Publishing workflow (`.github/workflows/publish.yml`).

### Changed
- Migrated code root from `scripts/` to standard `src/pdl_taskmaster/` package layout.
- Moved tests from `scripts/tests/` to `tests/`.
- Decoupled `mlflow` into an optional extra (`pdl-taskmaster[tracking]`), keeping the core dependency tree lean (`pydantic` only).

---

## [2.3.0] - 2026-09-17

Full release documentation: [`docs/releases/v2.3.0.md`](docs/releases/v2.3.0.md)

### Added
- Centralized version-pinned Normative Store architecture under `~/.pdlt/versions/v2/contracts/` (ADR-0008).
- Proportional reasoning budgets (ADR-0006) for Anthropic Claude 3.7 Sonnet and OpenRouter reasoning models.
- Connected dual-gate evaluation coupling the 27-case adversarial battery (F6) with the 13-case positive fidelity battery (Track P).
- Automated clause-coverage verifier invariant (Decision D28) asserting 100% contract binding across normative standards.
- Canary-shape generalization pass (Decision D29) sanitizing canonical UUIDs, high-entropy hex sequences, and synthetic prefixes.
- Interactive REPL fast paths (Track U / U1): `/confirm`, `/revise <feedback>`, and `/stop`.

### Changed
- Transitioned from static `workspace-template` scaffolding to dynamic, on-demand stage materialization.
- Completely purged legacy in-band evidence delimiters (`<<<EVIDENCE>>>`) in favor of strict JSON schema field isolation (Decision D27 / D5).
