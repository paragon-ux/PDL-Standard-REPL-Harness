# PDL-Standard-REPL-Harness

Clean standalone R6S / Phase-5 PDLt REPL harness, extracted from the qualified
source repositories. This repository is the published R6S REPL baseline; it is
not the Phase 6-EV implementation and not a Host Tool overlay.

## Install

Requirements: Python 3.11+ (stdlib only for the recorded path).

```powershell
cd C:\Users\USER\Desktop\Frameworks\PDL-Standard-REPL-Harness
python -m pip install -r requirements-mlflow.txt   # optional, only for /mlflow
```

No editable installs or PYTHONPATH changes are required. Run every command from
this repository root.

## Deterministic baseline verification

```powershell
python scripts\verify_repl_baseline.py
python -m pytest tests -q
```

The verifier checks required runtime/instructional files, imports, fixture
hashes, source-repository isolation, a fresh-workspace G06 lifecycle
(Prompt -> Plan -> execute -> result), and resume of the newly created
workspace. All workspaces are temporary.

## Interactive REPL (recorded / deterministic)

```powershell
python -m host.repl --candidate-repo . --worker recorded `
  --eval-root . --evidence fixtures\r4-recorded-worker\recorded-cases.json `
  --case-ids G06 --new-session
```

Supported commands: `/help`, `/status`, `/session`, `/new`, `/resume`,
`/mlflow [on|off]`, `/tokens [on|off]`, `/timeout [seconds]`, `/model [name]`,
`/worker [codex|recorded]`, `/sandbox [read-only|workspace-write]`,
`/workdir [path]`, `/transcript [path]`, `/quit`.

Normal text submits a task; the recorded worker replays the qualified G06 (full
lifecycle) or A02 (prompt revision) session. Use `/new` or `--new-session` for
a fresh workspace; use `/resume <session-id>` or `--session-id <id>` to resume.

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
- `SOURCE_PROVENANCE.json` — per-file provenance (source repo, HEAD, hashes,
  BYTE_IDENTICAL vs ADAPTED)

## Provenance

See `SOURCE_PROVENANCE.json` for source repositories, HEADs, per-file SHA-256,
and every adaptation required for standalone operation.