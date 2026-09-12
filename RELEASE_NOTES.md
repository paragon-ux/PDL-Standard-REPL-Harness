# Release Notes — v2.0.0

**PDL-Standard-REPL-Harness (PDL Taskmaster)** · 2026-09-12 · base: `r6s-repl-baseline-v1`

Major version bump: new live worker path with contract-wiring and
efficiency-control changes. Recorded-fixture behavior and the protocol
contract itself are unchanged; the recorded path remains byte-identical
deterministic replay.

## Highlights

- **SEM-05 "Message-act attribution"** added to the Semantic Input Standard
  with PLAN-09 contract wiring: a user message that itself performs a social
  act (greeting, thanks, apology, farewell) is now attributed to the user as
  actor. Live-verified on the previously-failing greeting case: prompt
  pseudocode now reads "The user performs a greeting" instead of an
  agent-actor paraphrase.
- **New live API worker** (`--worker api`): direct OpenAI-compatible
  `/responses` HTTP worker with Codex-CLI-style key resolution (Machine/User
  scope via short-lived PowerShell, key never in-process env), token
  telemetry, and no coding-agent scaffold overhead.
- **Per-operation reasoning control**: `--api-reasoning-operation OP=EFFORT`
  (repeatable) and `--api-reasoning-effort`. Review-stage operations run
  reasoning-free with identical classification outcomes.
- **Compact projection rendering** (`--render-compact` / `--render-pretty`):
  compact is the default for `--worker api` (~20% fewer input tokens,
  byte-identical parsed documents); recorded replay stays pretty and rejects
  compact with a clear error.
- **Cache-order wire rendering** (`--cache-order-render`, opt-in): same-shape
  calls share a byte-identical prompt prefix for provider prefix caching.
- **MLflow worker attribution fix**: session logs now record the actual
  worker profile (`api` vs `codex`) instead of a hardcoded `codex`.

## Measured efficiency (GLM 4.7 via OpenRouter, `hi` lifecycle)

| Configuration | Total tokens | Wall-clock |
|---|---|---|
| Baseline (pretty render, provider-default reasoning) | 12,916 | 80.4s |
| **Shipped optimum (compact render + reviews=none)** | **9,992 (−22.6%)** | **−50% on paired run** |

Full per-call data, NO-GO verdicts (draft-stage low reasoning, aggressive
static-prefix cache strategy, review-scope clause subset), and hidden
findings: `docs/EFFICIENCY_REPORT.md`.

## New flags

| Flag | Worker | Effect |
|---|---|---|
| `--api-reasoning-effort low\|medium\|high` | api | global reasoning effort override |
| `--api-reasoning-operation OP=EFFORT` (repeatable) | api | per-operation override; `none` disables reasoning for that operation |
| `--render-compact` / `--render-pretty` | any | projection wire format; compact default for api, rejected for recorded |
| `--cache-order-render` | api | cache-friendly key reordering; parsed content identical |

## Other changes

- `scripts/log_live_session.py`: `--worker-profile` flag; the REPL passes the
  active worker identity so MLflow params are correctly labeled.
- `scripts/control_api_call.py`: plain-call control harness used for
  protocol-vs-plain API comparisons (boundary A/B work).
- SEM-05 fixture and wiring tests (`tests/test_sem05_wiring.py`, 4 tests).

## Verification

- `python -m pytest tests -q` — 9 passed, 2 skipped.
- `python scripts/verify_repl_baseline.py` — deterministic G06 lifecycle +
  resume verification unchanged and passing.
- Live SEM-05 check on the previously-failing `hi` case: PASS (user-as-actor
  pseudocode, protocol closes `CLOSED_SUCCESS`).
- Recorded-fixture replay unchanged: full suite green with compact defaults
  active; `--worker recorded --render-compact` raises `SystemExit`.

## Upgrade notes

- No contract or fixture changes are required on upgrade; the vendored
  fixture replays identically.
- MLflow users: runs logged before this release may show
  `worker_profile=codex` for api-worker sessions; new runs are labeled
  correctly.
- Set `OPENROUTER_API_KEY` at Machine or User scope (or pass `--api-key-env`)
  for the api worker; the key is resolved per call, never cached in-process.