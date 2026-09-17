# PDL-Standard-REPL-Harness (PDL Taskmaster)

The standalone REPL harness for the PDLt fidelity protocol: interpretation
before execution, standards compiled into every model call, and a
user-owned mechanical confirmation boundary.

**Why this exists:** read [`docs/architecture/framing.md`](architecture/framing.md) —
the alignment frame. The harness enforces task fidelity (the requester's
meaning, confirmed and enforced) and prompt-injection defense (quoted and
pasted content stays data, never instruction) with one mechanism. Live
evidence includes a boundary test where the identical model on a plain API
call leaked 2/5 injection probes while the protocol arm held 0/5.

## Repository layout

```text
contracts/                 the normative Brain — standards, contracts, schemas (immutable)
confirm-with-pseudocode/   bootstrap skill entrypoint used by the protocol
scripts/                   all executable Python (Hands & Feet)
  host/                    REPL host and application wiring
  runtime/                 session engine, context compiler, normative store, workspace
  controller/              deterministic mechanical controller
  providers/               worker boundary: api / recorded / codex
  observation/             JSONL telemetry sinks
  tracking/                optional MLflow session logger (post-hoc, non-authoritative)
  eval/                    adversarial battery, fidelity scoring, qualified batch runner
  verify/                  deterministic baseline verification entry point
  tests/                   pytest suite
docs/                      site-ready documentation
  architecture/            framing.md, protocol v2 specs
  operations/              eval metrics, efficiency report
  governance/              roadmap, experiment decision register (D0–D27)
  adr/ trd/                internal append-only provenance (gitignored)
```

Historical run ledgers, recorded fixtures, and evaluation archives live in the
external sibling archive (`PDL-Standard-Archive/`); see
[`PDLt/docs/proposed/repo-restructure-plan.md`](../../../Downloads/PDLt/docs/proposed/repo-restructure-plan.md).
Recorded-mode fixtures resolve via `PDLT_FIXTURES_PATH`; evaluation runs via
`PDLT_RUNS_ROOT`.

## Install

Requirements: Python 3.11+ (stdlib only for the recorded path).

```powershell
cd PDL-Standard-REPL-Harness
python -m pip install -r requirements-test.txt      # required to run tests (pytest)
python -m pip install -r requirements-mlflow.txt    # optional, only for /mlflow logging
```

Run every command from this repository root.

## Deterministic baseline verification

```powershell
set PDLT_FIXTURES_PATH=C:\...\PDL-Standard-Archive\fixtures-r4-recorded-worker
python scripts\verify\verify_repl_baseline.py
python -m pytest scripts\tests -q
```

The verifier checks required runtime/instructional files, imports, the
zero-template workspace invariant (S2), fixture hashes, REPL subprocess-script
presence, source-repository isolation, a fresh-workspace G06 lifecycle
(Prompt → Plan → execute → result), and resume of the newly created workspace.
All verifier workspaces are temporary.

## Interactive REPL (recorded / deterministic)

```powershell
python -m scripts.host.repl --candidate-repo . --worker recorded `
  --evidence %PDLT_FIXTURES_PATH%\recorded-cases.json `
  --case-ids G06 --new-session
```

Recorded mode is **exact deterministic replay**: it responds only to the exact
interaction sequences captured in the fixture (G06: full lifecycle; A02:
prompt revision). Use `--quit` to exit (there is no `/exit` command).

Supported commands: `/help`, `/status`, `/session`, `/new`, `/resume`,
`/mlflow [on|off]`, `/tokens [on|off]`, `/timeout [seconds]`, `/model [name]`,
`/worker [api|codex|recorded]`, `/config (codex only)`, `/sandbox (codex only)`,
`/workdir [path]`, `/transcript [path]`, `/quit`.

Fast-path review commands: `/confirm`, `/revise <feedback>`, `/stop`.

## Live API worker path (default)

```powershell
# Default worker is 'api' with model 'z-ai/glm-4.7'
python -m scripts.host.repl --candidate-repo . --new-session
```

`--worker api` sends the compiled projection directly to an OpenAI-compatible
`/responses` endpoint (`instructions` =
`scripts/runtime/worker-bootstrap.txt`) with no tool definitions, sandbox, or
agentic system prompt attached.

### Efficiency flags (`--worker api`)

- `--api-reasoning-effort low|medium|high` — global reasoning override.
- `--api-reasoning-operation OP=EFFORT` (repeatable) — per-operation override;
  the proportional reasoning taxonomy (ADR-0006) is wired by default via
  model classification.
- `--render-compact` / `--render-pretty` — projection serialization (compact
  is the default for `--worker api`).
- `--cache-order-render` — opt-in wire reordering for provider prefix caching.

See [`docs/operations/efficiency-report.md`](operations/efficiency-report.md)
for per-call data and NO-GO verdicts.

## Adversarial evaluation & measurement (M1 / F6)

```powershell
python scripts\eval\run_qualified_batch.py --case-id BND-00 --stub --trials 1
python scripts\eval\run_qualified_batch.py --case-id BND-00 --trials 1 --model z-ai/glm-4.7
python scripts\eval\compare_eval_runs.py <summary.json>
```

The battery manifest and prior run ledgers resolve via `PDLT_RUNS_ROOT`
(default: the sibling `PDL-Standard-Archive/runs` directory). Measured
baselines: [`docs/operations/eval-metrics.md`](operations/eval-metrics.md).

## Layout notes

- Historical run artifacts (`runs/`, `mlruns/`) and recorded fixtures are
  **not** runtime dependencies and live outside the repository. The optional
  MLflow tracking store defaults to the external archive too
  (`PDL-Standard-Archive/mlflow/mlflow.db`; override with `PDLT_MLFLOW_DB`,
  legacy fallback: repo-root `mlflow.db`).
- Workspaces are zero-template and dynamic (ADR-0008): fresh runs scaffold
  only `state/`, `events/`, `stages/`, `shared/`.
- `SOURCE_PROVENANCE.json` records per-file provenance (source repo, HEAD,
  hashes, BYTE_IDENTICAL vs ADAPTED) from the qualified extraction.