# PDL-Standard-REPL-Harness

Clean standalone R6S / Phase-5 PDLt REPL harness, extracted from the qualified
source repositories. This repository is the published R6S REPL baseline; it is
not the Phase 6-EV implementation and not a Host Tool overlay.
## Baseline release

Commit `r6s-repl-baseline-v1` is the published clean R6S / Phase-5 PDLt REPL
harness baseline. It contains only the minimal standalone runtime, REPL,
worker boundary, vendored deterministic fixture, focused tests, verifier, and
provenance needed to reproduce the qualified path. It is **not** the future
Host Tool overlay, Phase 6-EV work, or an evaluation/evidence archive.

## Install

Requirements: Python 3.11+ (stdlib only for the recorded path).

```powershell
cd C:\Users\USER\Desktop\Frameworks\PDL-Standard-REPL-Harness
python -m pip install -r requirements-test.txt      # required to run tests (pytest)
python -m pip install -r requirements-mlflow.txt    # optional, only for /mlflow logging
```

No editable installs or PYTHONPATH changes are required. Run every command from
this repository root.

## Deterministic baseline verification

```powershell
python scripts\verify_repl_baseline.py
python -m pytest tests -q
```

The verifier checks required runtime/instructional files, imports, fixture
hashes, REPL subprocess-script presence, source-repository isolation, a
fresh-workspace G06 lifecycle (Prompt -> Plan -> execute -> result), and resume
of the newly created workspace. All verifier workspaces are temporary.

The pytest suite adds focused lifecycle tests and a full REPL command-loop
integration test (`tests/test_repl_integration.py`) that drives the real
terminal parser through `/help`, `/status`, `/session`, `/worker recorded`,
`/mlflow`, `/new`, `/resume`, and `/quit`.

## Interactive REPL (recorded / deterministic)

```powershell
python -m host.repl --candidate-repo . --worker recorded `
  --evidence fixtures\r4-recorded-worker\recorded-cases.json `
  --case-ids G06 --new-session
```

Recorded mode is **exact deterministic replay**: it responds only to the exact
interaction sequences captured in the vendored fixture (G06: full lifecycle;
A02: prompt revision). Arbitrary input such as `hi` is expected to raise
`ReplayMissError`, because the worker is keyed to exact operation + prompt
hash. Use the fixture's exact turns for deterministic testing; use the live
Codex worker for generative interaction.

Use `/quit` to exit (there is no `/exit` command).

Supported commands: `/help`, `/status`, `/session`, `/new`, `/resume`,
`/mlflow [on|off]`, `/tokens [on|off]`, `/timeout [seconds]`, `/model [name]`,
`/worker [codex|recorded]`, `/sandbox [read-only|workspace-write]`,
`/workdir [path]`, `/transcript [path]`, `/quit`.

## Sessions and persistence

`/new` creates a session directory immediately, but `session.json` is written
**lazily**: the workspace and pointer materialize on the first protocol turn.
A brand-new session with no turns has no `session.json` and no fabricated
workspace — this matches the source REPL and is intentional.

Use `/new` or `--new-session` for a fresh workspace; use
`/resume <session-id>` or `--session-id <id>` to resume a completed session.

## MLflow (optional)

MLflow logging is post-hoc and non-authoritative; the protocol never requires it.

### Setup

```powershell
python -m pip install -r requirements-mlflow.txt
```

### Enabling logging

- Answer `y` to `Log this session to MLflow on exit?` at REPL startup, or
- start with `--mlflow`, or
- toggle at runtime with `/mlflow on`.

### What happens

When logging is on, the REPL logs the closed session via
`scripts/log_live_session.py` on `/new`, `/resume`, `/worker`, and `/quit`. The
logger creates a local SQLite tracking store at `mlflow.db` (gitignored), under
experiment `PDL-R2S`, and prints:

```text
LIVE_SESSION_MLFLOW_RUN <run-id> session=<session-id> records=<n>
```

Only sessions that completed at least one protocol turn are logged (the
`session.json` pointer is written lazily on the first turn; a brand-new session
with no turns has nothing to log and reports `session.json missing`, which is
expected).

### Verify

```powershell
python -m pytest tests\test_mlflow_logger.py -q
```

### Inspect runs

```powershell
mlflow ui --backend-store-uri "sqlite:///$((Get-Location).Path.Replace('\','/'))/mlflow.db"
```

Then open http://localhost:5000 to browse the `PDL-R2S` experiment.

## Live worker path (optional)

```powershell
python -m host.repl --candidate-repo . --worker codex --model deepseek-v4-flash --new-session
```

The live path uses the Codex CLI (`codex exec`) with read-only sandbox and
approval `never` by default. Provider/model selection and credentials are
external harness options; no credentials are stored in this repository.

## Layout

- `host/`, `observation/`, `providers/`, `tracking/` — REPL, host, observation,
  worker boundary, optional MLflow indexing
- `runtime/`, `controller/`, `contracts/`, `workspace-template/` — qualified
  session/runtime path, controller, standards, and fresh-workspace template
- `confirm-with-pseudocode/` — bootstrap skill entrypoint used by the protocol
- `fixtures/r4-recorded-worker/` — vendored deterministic recorded fixture
- `scripts/verify_repl_baseline.py` — one deterministic verification entry point
- `scripts/log_live_session.py` — optional MLflow session logger
- `SOURCE_PROVENANCE.json` — per-file provenance (source repo, HEAD, hashes,
  BYTE_IDENTICAL vs ADAPTED)

## Run artifacts

Directories under `runs/` and `*.log` files are generated session/output
artifacts, not runtime dependencies. Historical run directories must never
become runtime dependencies; fresh workspaces are created at runtime.

## Provenance

See `SOURCE_PROVENANCE.json` for source repositories, HEADs, per-file SHA-256,
and every adaptation required for standalone operation.