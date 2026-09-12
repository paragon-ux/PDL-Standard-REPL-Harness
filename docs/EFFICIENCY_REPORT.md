# PDL-Standard-REPL-Harness — Efficiency Report

**Date:** 2026-09-12 · **Model:** `z-ai/glm-4.7` via OpenRouter · **Case:** `hi`
greeting lifecycle (DRAFT_PROMPT → INTERPRET_PROMPT_REVIEW → DRAFT_PLAN →
INTERPRET_PLAN_REVIEW → EXECUTE) · **Worker:** `--worker api`

All numbers are from live MLflow-telemetered sessions (`runs/live-sessions/`,
experiment `PDL-R2S`), per-call usage read from `observations/repl-session.jsonl`.
n=1–2 per configuration; these are engineering measurements, not qualified
R2S measurement conditions (every live session self-labels
`DEVELOPMENT / LIVE DEMONSTRATION; NOT A QUALIFIED R2S MEASUREMENT CONDITION`).

## Shipped levers (verified)

### 1. Per-operation reasoning control — `--api-reasoning-operation OP=EFFORT`

Repeatable flag; `EFFORT` ∈ `none|low|medium|high`; per-op wins over global
`--api-reasoning-effort`; `none` sends `reasoning:{enabled:false}`.

Discovery that motivated it: the two `INTERPRET_*_REVIEW` calls — whose entire
job is classifying the user's one-line confirmation — were consuming **41% of
session tokens and ~32% of wall-clock** because they received the full
standards projection plus a full reasoning budget.

Measured ('hi' session, paired):

| Call | Baseline | `=none` |
|---|---|---|
| INTERPRET_PROMPT_REVIEW | 14.1s | 1.8s |
| INTERPRET_PLAN_REVIEW | 17.8s | 3.8s |

Review intents identical (`ACCEPT_CURRENT` both arms). **Status: shipped.**

### 2. Compact projection rendering — `--render-compact` / `--render-pretty`

Compact is the **default for `--worker api`**; `--render-pretty` restores the
pretty wire format; `--worker recorded` rejects compact (fixture replay hashes
the full pretty prompt). Parsed documents are byte-identical after
`json.loads` (asserted programmatically).

Measured (paired 'hi' session): session input tokens **9,369 → 7,517
(−19.8%)**. **Status: shipped.**

### 3. Cache-order wire rendering — `--cache-order-render` (opt-in, small win)

Worker-side key reordering (schema + clauses first, volatile binds and
operation id last). Parsed content identical. The two REVIEW calls (same
20-clause set + same schema) share a **7,725-char byte-identical prefix**
(previously ~255 chars), enabling provider prefix-cache reuse between them.
**Status: shipped, opt-in; free, pays only when provider routing cooperates.**

## Evaluated and rejected

### 4. Review-scope clause subset — NO-GO (user decision)

Dropping REVIEW-09..14 + TASK-01/02 from review projections would save ~1.1k
chars/call but risks classification quality on edge cases (mixed changes,
cancel-plus-new-task) and rewrites contract `requirements` lists (manifest
hash churn). **User decision: keep the full clause set. Not implemented.**

### 5. Draft-stage low reasoning — NO-GO (measured)

`DRAFT_PROMPT=low` / `DRAFT_PLAN=low` on top of the shipped configuration,
two runs vs the compact+review-none run:

| Configuration | Tokens | Latency |
|---|---|---|
| baseline (pretty, default reasoning) | 12,916 | 80.4s |
| **compact + reviews=none (shipped optimum)** | **9,992 (−22.6%)** | 86.1s |
| + drafts=low (run 1) | 11,770 | 101.8s |
| + drafts=low (run 2) | 10,916 | 124.6s |

Draft-stage reasoning is the actual semantic work: at `low`, GLM 4.7 produced
*longer* outputs and higher wall-clock. **Verdict: do not use; documented in
README.**

### 6. Aggressive cache strategy (full static-prefix) — NO-GO (measured)

Design: byte-identical ~8.6k-token static block (full clause library + all
operation schemas) as `instructions` for every call, per-op dispatch envelope
as `input`. The prefix cache engaged mechanically (97% cached on repeat sends
of identical prompts), but on two identical 5-call probe sessions:

- Run 1: **39.0%** token-weighted hit rate (3 of 5 calls missed, back-to-back,
  byte-identical prefix) → ~3.2× the cost of the current design
- Run 2: **98.8%** hit rate → ~45% cheaper

Break-even at a 10× cache discount requires >91% sustained hits. OpenRouter
instance routing does not guarantee warm-prefix placement (also observed: an
exact byte-identical prompt resend missing entirely ~40 minutes after its
first send, then hitting at 97% on the second resend). **Verdict: routing
lottery; not shipped.** Re-tested conclusion: caching itself works on this
key; session-level cache reuse on OpenRouter is opportunistic.

## Hidden findings from the cost passes

- **No retry loop** in the model-call path — no hidden multi-send cost.
- **`_split_prompt` is render-shape-agnostic** — splits on the bootstrap
  prefix only; verified safe under compact rendering.
- **Recorded-fixture coupling:** `RecordedWorker` matches by
  `(operation, sha256(full_pretty_prompt))` — any render change silently
  breaks replay. The `--worker recorded` + `--render-compact` guard converts
  that from silent corruption into a clear `SystemExit`.
- **Live sessions receive ~0 provider cache hits** even when content repeats;
  hits observed only on identical back-to-back or warm-instance resends.

## Bottom line

Shipped configuration (compact render default + `INTERPRET_*_REVIEW=none`):
**~−23% total tokens, −50% wall-clock on the paired run, identical protocol
outcomes**, with the aggressive cache strategy and draft-low both measured and
rejected. Remaining unshipped ideas: none with positive expected value at
current provider behavior; revisit if OpenRouter stabilizes cache affinity or
GLM changes default reasoning behavior.