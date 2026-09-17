# INSTALLATION.md — Agentic Setup & Live API-Worker Runbook

Instructions for an **autonomous agent** (or a human following the same
steps) to stand up this harness and execute **live runs** against the API
worker. Every step has a verification gate: do not proceed past a failed
gate; report the failure output verbatim.

Shell syntax below is PowerShell. For bash/zsh: `set VAR=val` →
`export VAR=val`, backtick line-continuations → `\`.

---

## 1. Prerequisites

| Requirement | Check | Notes |
|---|---|---|
| Python 3.11+ | `python --version` | Standard library only for the recorded path |
| Repo checkout | `cd PDL-Standard-REPL-Harness` | **Run every command from the repo root** |
| pytest | `python -m pip install -r requirements-test.txt` | Only needed to run the test suite |
| MLflow (optional) | `python -m pip install -r requirements-mlflow.txt` | Only for `/mlflow` session logging |
| `OPENROUTER_API_KEY` | set in environment | Required for **any** live (`--worker api`) run; never needed for recorded/verified runs |

## 2. Environment variables

| Variable | Required for | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | live runs | API key sent as `Authorization` bearer by `ApiWorker` |
| `PDLT_FIXTURES_PATH` | recorded mode + verifier | Points at the recorded-fixture directory (sibling archive), e.g. `C:\path\to\PDL-Standard-Archive\fixtures-r4-recorded-worker` |
| `PDLT_RUNS_ROOT` | evaluation runs | Where run ledgers/adversarial battery/probe results are written (sibling archive `runs/`); point at any writable results directory |
| `PDLT_MLFLOW_DB` | optional | MLflow SQLite store location |

Runtime rule: **no run artifacts are written inside the repo** unless
`PDLT_RUNS_ROOT` is unset *and* no sibling archive exists. Workspaces are
temporary unless you pass `--workspace-root`.

## 3. Pre-flight gates (offline, no network, no key needed)

```powershell
set PDLT_FIXTURES_PATH=C:\path\to\PDL-Standard-Archive\fixtures-r4-recorded-worker
python scripts\verify\verify_repl_baseline.py        # GATE: must print "REPL BASELINE VERIFICATION PASS"
python -m pytest scripts\tests -q                    # GATE: all passed, 1 skipped
```

If either gate fails, stop — the installation is broken. Do not "fix" by
editing `contracts/`; contract bytes are versioned and hash-pinned.

## 4. Live run — quick start (REPL)

```powershell
python -m scripts.host.repl --candidate-repo . --new-session
```

- Default worker is `api`, model `z-ai/glm-4.7`, endpoint
  `https://openrouter.ai/api/v1` (override: `--api-base-url`,
  `--api-key-env`, `--model`).
- The worker receives **exactly the compiled projection** on an
  OpenAI-compatible `/responses` call — no tools, no sandbox, no agentic
  system prompt. Do not add any (see whitepaper §3, instruction-lightness).
- Useful flags: `--api-reasoning-effort`, `--api-reasoning-operation
  OP=EFFORT`, `--api-model-operation OP=MODEL`, `--cache-order-render`,
  `--render-compact|--render-pretty`, `--worker-timeout`.
- REPL commands: `/status /help /session /new /resume /model /worker /tokens /quit`;
  fast paths `/confirm`, `/revise <feedback>`, `/stop`. Exit with `/quit`
  or `--quit` (there is no `/exit`).

## 5. Calling the API worker programmatically (reusable agent pattern)

The canonical way for an agent to drive a full protocol lifecycle is
`PDLtHost` + `ApiWorker`. The gate loop below is the same pattern used by
`scripts/eval/run_dual_gate_probe.py` (refer to it for the hardened
version with transport retries).

```python
import sys
from pathlib import Path
ROOT = Path(r"C:\path\to\PDL-Standard-REPL-Harness")
sys.path.insert(0, str(ROOT))

from scripts.providers.api_worker import ApiWorker
from scripts.host.app import PDLtHost

worker = ApiWorker(
    model="z-ai/glm-4.7",
    repo_root=ROOT,
    timeout=45.0,
    reasoning_effort="none",                      # or per-op mapping, see probes
    reorder_keys_for_cache=True,                  # opt-in prefix-cache reordering
)

host = PDLtHost(
    ROOT,
    worker=worker,
    workspace_root=ROOT / "runs" / "my-run" / "workspaces",  # or any scratch dir
    observation_dir=ROOT / "runs" / "my-run" / "observations",
    run_id="my-run",
    render_compact=True,                          # matches eval-tier probes
).start()

turn = host.handle("<the user's task text>")      # turn 1: activation + interpretation
steps = 0
while not turn.closed and steps < 8:
    steps += 1
    stage = (host.status().get("controller_state") or {}).get("stage")
    if stage in {"PROMPT_REVIEW", "PLAN_REVIEW"}:
        turn = host.handle("Confirm.")            # user confirms the artifact
    elif stage == "WAITING_INPUT":
        turn = host.handle("Proceed with execution.")
    elif stage in {"CLOSED_SUCCESS", "CLOSED_CANCELLED"}:
        break
    else:
        turn = host.handle("Confirm.")

deliverable = turn.text                           # the executed result
host.close()                                      # flushes workspace state/events
```

Rules for agents driving lifecycles:

1. **Never fabricate controller transitions.** Only send user-role
   messages: the task text, `Confirm.`, `/revise`-equivalent feedback, or
   `Proceed with execution.` The mechanical controller owns everything else.
2. **Confirmation escalation.** Some models classify a bare `Confirm.`
   as non-progression. After 2 unproductive review turns, escalate once:
   `"I explicitly confirm the artifact above as the user. This is a positive
   confirmation. Proceed."` (see `run_dual_gate_probe.py`).
3. **Transport faults retry; wire faults don't.** Retry on
   `TransportError` (empty output, 429/5xx) with backoff (5s × attempt,
   3 attempts). A `WireError`/conformity violation is a **scored outcome** —
   record it, don't mask it.
4. **Extract the deliverable from the workspace**, not from memory:
   the confirmed result lives at
   `<workspace>/{turns/turn_###/}stages/50_execution/output/current.md`
   (hierarchical sessions since Phase 9; glob both layouts or use
   `WorkspaceRun.open(...).stages_root()`).

## 6. Ready-made evaluation probes (agent-invokable)

```powershell
# D29 canary-shape containment probe (verification tier, N=1 paired, 2 arms)
python scripts\eval\run_canary_shape_probe.py --model z-ai\glm-4.7
# GATE: "3/3 CONTAINED" on the protocol arm; control-arm natural echo is
# expected and is calibration data, not a failure.

# Connected dual-gate probe (adversarial + fidelity, paired)
python scripts\eval\run_dual_gate_probe.py --model qwen\qwen3-coder-30b-a3b-instruct

# Single adversarial battery case (stub = offline; omit for live)
python scripts\eval\run_qualified_batch.py --case-id BND-00 --stub --trials 1
```

Probe results are written under `$PDLT_RUNS_ROOT` (e.g.
`canary_shape_probe/results-<model>.json`). Results are evidence-tier
unless the run specification says otherwise (see ROADMAP, D20).

## 7. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `HTTP 401` on first call | Key unset/invalid | Check `OPENROUTER_API_KEY`; `ApiWorker` raises `TransportError: could not resolve ...` before the call if unset |
| `HTTP 404` model not found | Model id unavailable on the pinned provider | Pick an active id (ROADMAP M2 matrix); don't disable provider pinning silently |
| `HTTP 400 "Reasoning is mandatory for this endpoint"` | Model/endpoint requires reasoning (e.g. some Flash tiers) | Use a model that accepts `reasoning_effort: none`, or supply a per-op mapping |
| `TransportError ... empty output` | Provider returned `output: []` with tokens consumed | Retry with backoff (pattern in `run_dual_gate_probe.py` / `api_worker` retries) |
| `ReplayMissError` | Recorded worker got a prompt not in the fixture | Recorded mode replays **exact** sequences only; for free-form testing use `--worker api` |
| Verifier fails on fixture hash | Wrong/stale `PDLT_FIXTURES_PATH` | Point at the recorded-fixture directory matching this repo version |

## 8. Etiquette (binding for agents)

- Never modify `contracts/` (hash-pinned), `docs/governance/` decision
  records, or recorded fixtures.
- Never place secrets, canaries, or untrusted content into
  `contracts/`, instruction files, or the worker bootstrap — untrusted
  data enters only through task content at runtime; that is the mechanism
  under test.
- Run artifacts belong under `PDLT_RUNS_ROOT`; keep the repo tree clean
  (`git status` should be empty after an eval run).
- Record every live run's model id, endpoint, and date — an unrecorded
  run is not evidence.
