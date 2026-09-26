# PDL Taskmaster
*(PDL-Standard-REPL-Harness)*

A REPL harness that makes a language model interpret your request — in short, readable pseudocode — and wait for you to confirm it before anything runs. The same mechanism that catches a misread request also blocks prompt injection: anything quoted or pasted into a task is treated as data at read time and never promoted to an instruction.

**Why this exists:** [`docs/architecture/framing.md`](docs/architecture/framing.md) — the full case, including a live boundary test where the identical model, on one unprotected API call, leaked 2 of 5 injected probes while the protocol held 0 of 5. For the full mechanism, design history, and evidence: [`docs/architecture/whitepaper.md`](docs/architecture/whitepaper.md).

## Repository layout

```text
contracts/                 versioned standards, contracts, and schemas (normative source)
confirm-with-pseudocode/   bootstrap skill entrypoint used by the protocol
src/pdl_taskmaster/        clean Python package root
  host/                    REPL host, umbrella CLI (pdlt), and application wiring
  runtime/                 session engine, context compiler, 4-tier standards store, workspace
  controller/              deterministic mechanical controller
  providers/               model-worker boundary: api / recorded / codex
  observation/             JSONL telemetry sinks
  tracking/                optional MLflow session logger (post-hoc, non-authoritative)
  eval/                    adversarial battery, fidelity scoring, batch runner
  verify/                  deterministic baseline verification entry point
  contracts/               bundled package data contracts (Tier 4 normative store)
tests/                     pytest suite and vendored self-contained test fixtures
  fixtures/                vendored recorded cases and adversarial/fidelity batteries
docs/                      documentation
  architecture/            framing.md, whitepaper.md, protocol specs
  operations/              eval-metrics.md, efficiency-report.md
  governance/              roadmap.md, experiment-log.md (full decision history)
  adr/ trd/                background architecture-decision records (history, not required reading)
```

The package ships with self-contained test fixtures vendored under `tests/fixtures/`, enabling 100% offline testing. Historical run ledgers and large evaluation archives are kept in external archives outside this repository and resolve via `PDLT_FIXTURES_PATH` (fixtures) and `PDLT_RUNS_ROOT` (evaluation runs).

## Install

Requirements: Python 3.11+, Pydantic v2 (`pydantic>=2.5.0,<3.0.0`).

```powershell
# From PyPI (once published)
pip install pdl-taskmaster
# or using uv:
uv add pdl-taskmaster

# Development / editable installation:
cd PDL-Standard-REPL-Harness
pip install -e ".[test]"
# or with optional MLflow tracking:
pip install -e ".[test,tracking]"
```

Run every command from this repository root or anywhere when installed as a package.

## Umbrella CLI (`pdlt`)

When installed, the `pdlt` command line tool provides the complete entry point:

```powershell
pdlt --help                 # View CLI command options and REPL flags
pdlt version                # Print package version, protocol spec, and manifest hash
pdlt init --global          # Initialize standards in ~/.pdlt/versions/v2/contracts/
pdlt init --local           # Seed standards into ./contracts/ in current directory
pdlt verify                 # Run deterministic baseline verification gate
pdlt                        # Launch interactive REPL (default)
```

## Deterministic baseline verification

```powershell
pdlt verify                 # Deterministic baseline verifier
pytest                      # Run complete test suite (offline, 87 passed)
```

The verifier checks required runtime/instructional files, imports, the zero-template workspace invariant, fixture hashes, REPL subprocess-script presence, source-repository isolation, a fresh-workspace lifecycle test (prompt → plan → execute → result), and resuming that same workspace. All verifier workspaces are temporary.

## Interactive REPL (recorded / deterministic)

```powershell
pdlt --worker recorded --case-ids G06 --new-session
# or: python -m pdl_taskmaster.host.repl --worker recorded --case-ids G06 --new-session
```

Recorded mode is **exact, deterministic replay**: it only responds to the exact interaction sequences captured in the fixture (`G06`: full lifecycle; `A02`: prompt revision). Use `--quit` to exit — there's no `/exit` command.

Commands: `/help`, `/status`, `/session`, `/new`, `/resume`, `/mlflow [on|off]`, `/tokens [on|off]`, `/timeout [seconds]`, `/model [name]`, `/worker [api|codex|recorded]`, `/config` (codex only), `/sandbox` (codex only), `/workdir [path]`, `/transcript [path]`, `/paste` (or `"""`), `/quit`.

Fast-path review commands: `/confirm`, `/revise <feedback>`, `/stop`.

## Live model worker (default)

```powershell
# Default worker is 'api' with model 'z-ai/glm-4.7'
pdlt --new-session
# or: python -m pdl_taskmaster.host.repl --candidate-repo . --new-session
```

> **System 1 / System 2 Architecture Note**: Production default is `--worker api` (System 2, e.g. `z-ai/glm-4.7`). Local fast System 1 classification models are undergoing contrastive RLCD fine-tuning (ADR-0012) and fail-closed to System 2 via the confidence ladder if threshold ($0.85$) or top-2 margin ($0.40$) are unmet.

`--worker api` sends the compiled interpretation/plan directly to an OpenAI-compatible `/responses` endpoint (instructions bundled in `src/pdl_taskmaster/runtime/worker-bootstrap.txt`), with no tool definitions, sandbox, or agentic system prompt attached — deliberately; see the "instruction-lightness" finding in the whitepaper (§3).

### Efficiency flags (`--worker api`)

- `--api-reasoning-effort low|medium|high` — reasoning budget override, applied globally.
- `--api-reasoning-operation OP=EFFORT` (repeatable) — per-step override; sensible per-model defaults are already wired in (see whitepaper §4).
- `--api-model-operation OP=MODEL` (repeatable) — per-step model override, e.g. keep interpretation on a frontier model and route everything else to a cheaper instruction-following one.
- `--render-compact` / `--render-pretty` — how the interpretation/plan is serialized on the wire (compact is the default for `--worker api`).
- `--cache-order-render` — opt-in reordering for provider-side prefix caching.

Per-call cost data, and which optimizations were tried and rejected: [`docs/operations/efficiency-report.md`](docs/operations/efficiency-report.md).

## Adversarial evaluation

```powershell
python -m pdl_taskmaster.eval.run_qualified_batch --case-id BND-00 --stub --trials 1
python -m pdl_taskmaster.eval.run_qualified_batch --case-id BND-00 --trials 1 --model z-ai/glm-4.7
python -m pdl_taskmaster.eval.compare_eval_runs <summary.json>
```

The battery manifest and prior run ledgers resolve via `PDLT_RUNS_ROOT` (defaults to a sibling archive directory not included in this repository — point it at your own results directory to run the battery from scratch). Measured baselines so far: [`docs/operations/eval-metrics.md`](docs/operations/eval-metrics.md).

## Notes

- Run artifacts (`runs/`, `mlruns/`) and external evaluation archives are **not** runtime dependencies and are kept outside the repository. The optional MLflow tracking store follows the same pattern (override with `PDLT_MLFLOW_DB`; falls back to a repo-root `mlflow.db` if unset).
- Workspaces are zero-template and dynamic: a fresh run scaffolds only `state/`, `events/`, `stages/`, `shared/`, and stage folders materialize as they're needed (see whitepaper §5).
- `SOURCE_PROVENANCE.json` records per-file provenance (source repo, commit, hashes, byte-identical vs. adapted) from the original extraction.
- Internal architecture/technical decision records referenced elsewhere in these docs (`docs/adr/`, `docs/trd/`) are background only and not required reading to use the harness.

## Optional MLflow logging

MLflow logging is post-hoc and non-authoritative; the protocol never requires it. Enable it by answering `y` to the startup prompt, launching with `--mlflow`, or toggling with `/mlflow on`. When enabled, closed sessions are logged via `pdl_taskmaster.tracking.log_live_session` to a local SQLite store (default location follows the archive-resolution pattern described above) under experiment `PDL-R2S`, printing a `LIVE_SESSION_MLFLOW_RUN` line per logged session. Only sessions that completed at least one protocol turn are logged. Requires `pip install "pdl-taskmaster[tracking]"`.
