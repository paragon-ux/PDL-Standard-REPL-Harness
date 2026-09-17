# PDL Taskmaster
*(PDL-Standard-REPL-Harness)*

A REPL harness that makes a language model interpret your request — in short, readable pseudocode — and wait for you to confirm it before anything runs. The same mechanism that catches a misread request also blocks prompt injection: anything quoted or pasted into a task is treated as data at read time and never promoted to an instruction.

**Why this exists:** [`docs/architecture/framing.md`](docs/architecture/framing.md) — the full case, including a live boundary test where the identical model, on one unprotected API call, leaked 2 of 5 injected probes while the protocol held 0 of 5. For the full mechanism, design history, and evidence: [`docs/architecture/whitepaper.md`](docs/architecture/whitepaper.md).

## Repository layout

```text
contracts/                 versioned standards, contracts, and schemas (rarely change)
confirm-with-pseudocode/   bootstrap skill entrypoint used by the protocol
scripts/                   all executable Python
  host/                    REPL host and application wiring
  runtime/                 session engine, context compiler, standards store, workspace
  controller/              deterministic mechanical controller
  providers/               model-worker boundary: api / recorded / codex
  observation/             JSONL telemetry sinks
  tracking/                optional MLflow session logger (post-hoc, non-authoritative)
  eval/                    adversarial battery, fidelity scoring, batch runner
  verify/                  deterministic baseline verification entry point
  tests/                   pytest suite
docs/                       documentation
  architecture/            framing.md, whitepaper.md, protocol specs
  operations/              eval-metrics.md, efficiency-report.md
  governance/              roadmap.md, experiment-log.md (full decision history)
  adr/ trd/                background architecture-decision records (history, not required reading)
```

Historical run ledgers, recorded fixtures, and evaluation archives are kept in a separate archive outside this repository and are not part of this release. Recorded-mode fixtures resolve via `PDLT_FIXTURES_PATH`; evaluation runs via `PDLT_RUNS_ROOT`.

## Install

Requirements: Python 3.11+ (standard library only for the recorded path).

> **Setting up for live runs — or handing this to an autonomous agent?** [`INSTALLATION.md`](INSTALLATION.md) is the agent-oriented setup & runbook: environment gates, pre-flight verification, the reusable programmatic pattern for calling the API worker, ready-made probes, troubleshooting, and binding agent etiquette.

```powershell
cd PDL-Standard-REPL-Harness
python -m pip install -r requirements-test.txt      # required to run tests (pytest)
python -m pip install -r requirements-mlflow.txt    # optional, only for /mlflow logging
```

Run every command from this repository root. (Commands below use PowerShell syntax — swap `set VAR=val` and the backtick line-continuation for your shell's equivalent, e.g. `export VAR=val` and `\` on bash/zsh.)

## Deterministic baseline verification

```powershell
set PDLT_FIXTURES_PATH=C:\path\to\PDL-Standard-Archive\fixtures-r4-recorded-worker
python scripts\verify\verify_repl_baseline.py
python -m pytest scripts\tests -q
```

The verifier checks required runtime/instructional files, imports, the zero-template workspace invariant, fixture hashes, REPL subprocess-script presence, source-repository isolation, a fresh-workspace lifecycle test (prompt → plan → execute → result), and resuming that same workspace. All verifier workspaces are temporary.

## Interactive REPL (recorded / deterministic)

```powershell
python -m scripts.host.repl --candidate-repo . --worker recorded `
  --evidence %PDLT_FIXTURES_PATH%\recorded-cases.json `
  --case-ids G06 --new-session
```

Recorded mode is **exact, deterministic replay**: it only responds to the exact interaction sequences captured in the fixture (`G06`: full lifecycle; `A02`: prompt revision). Use `--quit` to exit — there's no `/exit` command.

Commands: `/help`, `/status`, `/session`, `/new`, `/resume`, `/mlflow [on|off]`, `/tokens [on|off]`, `/timeout [seconds]`, `/model [name]`, `/worker [api|codex|recorded]`, `/config` (codex only), `/sandbox` (codex only), `/workdir [path]`, `/transcript [path]`, `/quit`.

Fast-path review commands: `/confirm`, `/revise <feedback>`, `/stop`.

## Live model worker (default)

```powershell
# Default worker is 'api' with model 'z-ai/glm-4.7'
python -m scripts.host.repl --candidate-repo . --new-session
```

`--worker api` sends the compiled interpretation/plan directly to an OpenAI-compatible `/responses` endpoint (instructions = `scripts/runtime/worker-bootstrap.txt`), with no tool definitions, sandbox, or agentic system prompt attached — deliberately; see the "instruction-lightness" finding in the whitepaper (§3).

### Efficiency flags (`--worker api`)

- `--api-reasoning-effort low|medium|high` — reasoning budget override, applied globally.
- `--api-reasoning-operation OP=EFFORT` (repeatable) — per-step override; sensible per-model defaults are already wired in (see whitepaper §4).
- `--api-model-operation OP=MODEL` (repeatable) — per-step model override, e.g. keep interpretation on a frontier model and route everything else to a cheaper instruction-following one.
- `--render-compact` / `--render-pretty` — how the interpretation/plan is serialized on the wire (compact is the default for `--worker api`).
- `--cache-order-render` — opt-in reordering for provider-side prefix caching.

Per-call cost data, and which optimizations were tried and rejected: [`docs/operations/efficiency-report.md`](docs/operations/efficiency-report.md).

## Adversarial evaluation

```powershell
python scripts\eval\run_qualified_batch.py --case-id BND-00 --stub --trials 1
python scripts\eval\run_qualified_batch.py --case-id BND-00 --trials 1 --model z-ai/glm-4.7
python scripts\eval\compare_eval_runs.py <summary.json>
```

The battery manifest and prior run ledgers resolve via `PDLT_RUNS_ROOT` (defaults to a sibling archive directory not included in this repository — point it at your own results directory to run the battery from scratch). Measured baselines so far: [`docs/operations/eval-metrics.md`](docs/operations/eval-metrics.md).

## Notes

- Run artifacts (`runs/`, `mlruns/`) and recorded fixtures are **not** runtime dependencies and are kept outside the repository. The optional MLflow tracking store follows the same pattern (override with `PDLT_MLFLOW_DB`; falls back to a repo-root `mlflow.db` if unset).
- Workspaces are zero-template and dynamic: a fresh run scaffolds only `state/`, `events/`, `stages/`, `shared/`, and stage folders materialize as they're needed (see whitepaper §5).
- `SOURCE_PROVENANCE.json` records per-file provenance (source repo, commit, hashes, byte-identical vs. adapted) from the original extraction.
- Internal architecture/technical decision records referenced elsewhere in these docs (`docs/adr/`, `docs/trd/`) are background only and not required reading to use the harness.
- Local worker support (`--worker local`, targeting a warm local daemon) and a distillation flywheel for a bespoke, cheaper worker model are planned, not yet shipped — see [`docs/governance/roadmap.md`](docs/governance/roadmap.md) (Track L). `qwen/qwen3-coder-30b-a3b-instruct` is the open-weights model currently queued as the next cross-model check and distillation source; you can already point `--api-model-operation` at it today.

## Optional MLflow logging

MLflow logging is post-hoc and non-authoritative; the protocol never requires it. Enable it by answering `y` to the startup prompt, launching with `--mlflow`, or toggling with `/mlflow on`. When enabled, closed sessions are logged via `scripts/tracking/log_live_session.py` to a local SQLite store (default location follows the archive-resolution pattern described above) under experiment `PDL-R2S`, printing a `LIVE_SESSION_MLFLOW_RUN` line per logged session. Only sessions that completed at least one protocol turn are logged. Requires `python -m pip install -r requirements-mlflow.txt`.
