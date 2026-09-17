# Worker adapters

## Generic contract

`base.py` defines the generic `WorkerAdapter` contract:

```text
ModelRequest
    ->
raw model text
+ optional transport metadata
```

The adapter knows nothing about PDL wire validity. `OperationBridge` remains
the candidate-side authority for wire parsing.

## Live demonstration worker

`live_stub.py` is a deterministic non-recorded worker used for live-capability
tests. It is labeled:

```text
DEVELOPMENT / LIVE DEMONSTRATION WORKER
NOT A QUALIFIED R2S MEASUREMENT CONDITION
```

`codex_worker.py` is the live Codex-backed demonstration worker. It is also
labeled as a **LIVE SEMANTIC WORKER** and a development/live demonstration
worker; it is not a qualified R2S measurement condition and is not a coding
domain execution backend.

### Codex safety defaults

Normal local operation uses:

```text
approval mode = never
sandbox mode  = read-only
bypass        = OFF
```

`workspace-write` is opt-in (`/sandbox workspace-write` or
`--worker-sandbox workspace-write`) and remains constrained to an explicit
session/disposable workspace root. The dangerous bypass condition is a
separate startup-only mode intended only for externally hardened or
disposable execution environments; it is never an automatic fallback and is
not part of the Phase 0–5 seal.

### Codex telemetry

Machine-readable `codex exec --json` events are preferred. Structured usage is
recorded only when the JSON explicitly provides the field, prefixed as
`codex_cli_*`. If only plaintext `tokens used` is available, it is recorded as
`codex_cli_reported_total` with `usage_source=codex_cli_plaintext` and
`usage_exact=false`. Parsed totals are never mapped into provider-authoritative
`total_tokens`, `input_tokens`, `cached_tokens`, or `reasoning_tokens`.
Telemetry records the Codex CLI version, requested/observed model, sandbox
mode, approval mode, workdir, JSON mode, response/session identifier,
latency, usage source, and usage exactness. Credentials are never stored.

## Replay/qualification only

`recorded.py` and `fixtures.py` are replay/qualification utilities. They are
not the general-purpose worker contract and may reference historical evidence,
case IDs, and recorded turn sequences only because they exist to make
deterministic replay reproducible.
