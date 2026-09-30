# Efficiency Profile: Tested OpenRouter Reference Stack

**Date:** September 29, 2026 · **Release:** `v2.6.0-rc1`  
**Reference Stack:** `openai/gpt-oss-120b` (System 2) + `typesafe/jev-1.13` (System 1) via OpenRouter

---

## 1. Executive Summary

This explainer details the efficiency, latency, and cost profile of the **OpenRouter reference stack** verified for PDL Taskmaster `v2.6.0-rc1`. Among the model and provider configurations we evaluated on OpenRouter as of September 29, 2026, this paired stack demonstrated Pareto-efficient speed and cost:

- **System 2 (Reasoning & Synthesis):** `openai/gpt-oss-120b` (released last year), selected because it was the fastest model on OpenRouter (Cerebras consistently over 550 tokens/sec; next-leading providers consistently over 250 tokens/sec).
- **System 1 (Semantic Gating & Refusal):** `typesafe/jev-1.13`, providing non-generative classification in tens to hundreds of milliseconds.
- **Verification Milestone:** Verified end-to-end at **100.0% (105 / 105) PASS** with **0 regressions** in 1,947.8s on the 105-prompt catalogue in `PDLt-Test`.

PDLt's reasoning-through-fidelity result applies specifically to what was tested on this reference stack. It does not imply identical performance or behavioral parity on unverified models.

---

## 2. Component Specifications & Pricing

| Component | Model & Identifier | Harness Role | Provider & Speed | Pricing (as of 2026-09-29) | Source / Attribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System 2** | `openai/gpt-oss-120b` | Deliberative Prompt/Plan drafting and Python solver code synthesis | Cerebras: >550 tok/sec; other providers: >250 tok/sec | ~$0.03 / MTok input<br>~$0.17 / MTok output | [OpenRouter Provider Overview](https://openrouter.ai/openai/gpt-oss-120b#providers). Speeds and prices subject to provider variability. |
| **System 1** | `typesafe/jev-1.13` | Leading Skills routing, review intent classification, environment refusal | Vendor-stated response: 70 ms to 500 ms | $0.042 / MTok input ($42 / BTok)<br>Output: free | [OpenRouter / TypeSafe](https://openrouter.ai/typesafe/jev-1.13). TypeSafe vendor claim: "40x–200x faster for the same levels of frontier intelligence for System One shaped queries" ([TypeSafe Blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)). |

---

## 3. Empirical Telemetry: 105-Prompt Catalogue Benchmark

Across the complete 105-prompt test catalogue run (`run-20260929-132741`, 405 API calls total), host telemetry and OpenRouter provider logs yielded the following empirical distribution:

| Metric | Measured Value | Share of Total Time | Per-Prompt Mean |
| :--- | :---: | :---: | :---: |
| **Total Wall-Clock Time** | **1,947.8s** (~32.5 min) | 100.0% | **18.55s** |
| **Model API Waiting Time** | **1,672.5s** (~27.9 min) | **85.86%** | **15.93s** (avg 3.86 calls/prompt) |
| **Host & Sandbox Protocol Overhead** | **275.3s** (~4.6 min) | **14.14%** | **2.62s** |
| **System 1 Boundary Refusal Latency** | **1.4s – 1.9s** per refusal | — | **~1.65s** (Category 13 fast path) |
| **Estimated Catalogue API Cost** | **~$0.18 – $0.24** total | — | **~$0.0019 / prompt** |

Host overhead averages **2.62s per prompt**, which encompasses Windows Job Object creation, process isolation, synchronous multi-file workspace persistence across turns, cryptographic SHA-256 digest creation, and Pydantic validation. **85.9% of execution latency is direct upstream inference wait time.**

---

## 4. Caveats, Provider Variability & Backend Scope

- **Throughput & Price Volatility:** Token throughput and endpoint pricing are set by upstream providers and fluctuate over time. All quoted figures reflect conditions as of September 29, 2026.
- **Backend Schema Strictness:** Different OpenRouter backends exhibit varying grammar strictness. For example, engines such as Groq and Venice reject un-inlined `$defs`, `uniqueItems`, and certain Pydantic union shapes. While PDLt includes schema sanitization shims (`_sanitize_schema_for_grammar`), cross-backend wire compatibility must be verified per provider.
- **Code Block & Marker Formatting:** Synthesized output formatting differs across model families (`python` vs `py`, raw code vs fenced, presence of `### filename` headers). The harness provides alias tolerance, but unverified models may trigger unnecessary reconciliation retries.
- **Reasoning Floors:** Minimum viable reasoning budgets are model-dependent. While `gpt-oss-120b` operates reliably at `low` reasoning effort, earlier tests on GLM-4.7 demonstrated semantic collapse at `none`. Minimum floors for unverified models are unknown.
- **Roadmap Track M2:** Cross-model qualification across other model families (such as DeepSeek-V3, Qwen3-Coder, and Claude) is queued under Roadmap Track M2, with model-specific tuning, prompt adjustments, and empirical reports to follow.
