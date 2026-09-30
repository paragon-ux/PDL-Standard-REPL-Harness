# PDLt Prompt Catalogue Benchmark Report: 100.0% Pass Rate & Latency Analysis

**Date:** 2026-09-29  
**Model:** `openai/gpt-oss-120b` (low reasoning effort, `--api-structured-output`)  
**Router / System 1:** `typesafe/jev-1.13-20260917` (TypeSafe / ModernBERT)  
**Total Prompts:** 105 across 15 Categories  
**Pass Rate:** **100.0% (105 / 105)**  
**Total Wall-Clock Time:** 1,947.8s (~32.5 min)  
**Known Regressions Hit:** **0**  
**Run Artifacts:** [`catalogue-runs/run-20260929-132741`](file:///C:/Users/USER/Desktop/Frameworks/PDLt-Test/catalogue-runs/run-20260929-132741/SCOREBOARD.md)  

---

## 1. Official Catalogue Scoreboard

### Category Breakdown

| Category ID & Name | Prompts | Pass | Fail | Pass Rate | Mean Time (s) | Primary Stress Areas |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **01 `combinatorial_search`** | 7 | 7 | 0 | **100%** | 24.2s | Combinatorial search, witness polarity, disjoint partitions |
| **02 `data_structures`** | 7 | 7 | 0 | **100%** | 25.2s | Memory bounds, LRU/LFU cache, concurrent queues |
| **03 `systems_programming`** | 7 | 7 | 0 | **100%** | 21.2s | Zero-copy buffers, wire layouts, socket protocols |
| **04 `parsers_and_compilers`** | 7 | 7 | 0 | **100%** | 22.2s | AST construction, Pratt parsing, grammar ambiguities |
| **05 `algorithm_design`** | 7 | 7 | 0 | **100%** | 20.8s | Dynamic programming, branch-and-bound, graph flow |
| **06 `debugging_and_repair`** | 7 | 7 | 0 | **100%** | 7.5s | Off-by-one errors, concurrency race conditions |
| **07 `refactoring_and_design`** | 7 | 7 | 0 | **100%** | 19.9s | Modular decoupling, interface extraction, DRY |
| **08 `specification_extraction`** | 7 | 7 | 0 | **100%** | 13.4s | Quoted document extraction, regulatory mapping |
| **09 `adversarial_and_injection`** | 7 | 7 | 0 | **100%** | 9.5s | Jailbreak resistance, instruction hierarchy, bounds |
| **10 `multi_turn_and_revision`** | 7 | 7 | 0 | **100%** | 14.9s | Sequential user feedback, revision drift prevention |
| **11 `cross_domain_composition`** | 7 | 7 | 0 | **100%** | 45.1s | REST APIs + OpenAPI 3.0 specs + e2e test suites |
| **12 `domain_knowledge`** | 7 | 7 | 0 | **100%** | 17.6s | Distributed consensus, cryptography, formal specs |
| **13 `negative_and_impossible`** | 7 | 7 | 0 | **100%** | 9.1s | Fast refusal, negative witness certification |
| **14 `formal_verification`** | 7 | 7 | 0 | **100%** | 14.1s | Inductive invariants, SMT modeling, state proofs |
| **15 `performance_and_scale`** | 7 | 7 | 0 | **100%** | 13.6s | Scale limits, streaming payload memory bounds |

### Difficulty Distribution

| Difficulty Level | Total Prompts | Pass | Pass Rate |
| :--- | :---: | :---: | :---: |
| **Easy** | 7 | 7 | **100%** |
| **Medium** | 44 | 44 | **100%** |
| **Hard** | 43 | 43 | **100%** |
| **Adversarial** | 11 | 11 | **100%** |

---

## 2. Latency & Performance Anatomy

A key architectural question was whether the ~18.5s average prompt latency stems from protocol overhead or model inference round-trips. Empirical telemetry from the run cross-referenced with OpenRouter activity logs (`openrouter_activity_2026-09-29.csv`) resolves this question definitively:

### Macro Execution Split

```
Total Wall-Clock Time: 1,947.8s (100.0%)
├── Model API Waiting Time:         1,672.5s (85.86%)
└── Harness Protocol & Sandbox:       275.3s (14.14%) [2.62s / prompt]
```

### Per-Operation Model Latencies (405 API Calls Total)

| Operation | Total Calls | Total Time | Share of API Time | Mean Time | Median Time |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`EXECUTE`** | 94 | **1,009.8s** | **60.38%** | 10.74s | 7.92s |
| **`DRAFT_PROMPT`** | 110 | **288.8s** | **17.27%** | 2.63s | 2.31s |
| **`BOOTSTRAP_ANALYSIS`** | 95 | **174.5s** | **10.43%** | 1.84s | 1.50s |
| **`DRAFT_PLAN`** | 94 | **156.7s** | **9.37%** | 1.67s | 1.45s |
| **`DRAFT_EXECUTE`** | 10 | **32.1s** | **1.92%** | 3.21s | 3.10s |
| **`EMIT_RESULT_IR`** | 2 | **10.6s** | **0.63%** | 5.30s | 5.32s |

### Protocol Overhead Decomposition (2.62s / Prompt)
The remaining 14.1% of wall-clock time is accounted for by host-side guarantees:
1. **Isolated Sandbox Process Execution (~1.10s)**: Spawning clean `python.exe` subprocesses on Windows NTFS with CPU/memory quotas, executing solver scripts or test assertions, and capturing certified witness stdout.
2. **Synchronous Workspace History Persistence (~0.85s)**: Writing stage inputs, outputs, `compiled-projection.json`, `projection-manifest.json`, and `controller-state.json` across all turns.
3. **Mechanical Pydantic Verification (~0.35s)**: Result IR validation, domain schema checks, and SHA-256 requirement integrity digests.
4. **REPL Inter-Turn Event Loop (~0.32s)**: Stdin reading, bracketed paste handling, transcript updates.

---

## 3. The 4 Behavioral Archetypes

The 15 categories reflect four distinct behavioral profiles:

### Archetype A: Certified Algorithmic Solvers (Categories 01, 02, 05, 14, 15)
* **Exemplar**: `01-01` (Schur Triples Partition, n=45)
* **Execution Flow**: Prompt Ingestion $\to$ System 1 Classify (`VERIFIED_EXECUTION`) $\to$ System 2 Prompt & Plan $\to$ System 2 Python Solver Generation $\to$ Autonomous Host Sandbox Execution $\to$ Mechanical Witness Verification (`PositiveWitness` / `data.triples`).
* **Key Invariant**: Zero model self-grading. Truth is certified strictly by sandbox code execution.

### Archetype B: Fast-Path Refusals & Boundary Guards (Categories 09, 13)
* **Exemplar**: `13-05` (Sub-quadratic 3SUM) & `09-01` (System Instruction Override)
* **Execution Flow**: User Prompt $\to$ System 1 (Jev/ModernBERT) Bounds Detection conditioned on runtime environment bounds $\to$ Immediate Refusal Terminal Stage.
* **Latency**: **1.4s – 3.8s total** (1 call, 0 System 2 frontier tokens consumed). Saves ~85% of compute on invalid/harmful requests.


### Archetype C: Multi-File Cross-Domain Composition (Categories 03, 04, 07, 11)
* **Exemplar**: `11-07` (REST API Server + OpenAPI 3.0 Spec + Test Suite)
* **Execution Flow**: Multi-file synthesis requiring standard library `http.server`, valid YAML/JSON OpenAPI schemas, and end-to-end integration tests delivered in a unified Result IR with cross-file reconciliation.

### Archetype D: Document Ingestion & Multi-Turn Adaptation (Categories 08, 10)
* **Exemplar**: `08-06` (Regulatory Mapping) & `10-01` (API Revision)
* **Execution Flow**: Automatic extraction of quoted policy text and fenced code blocks into `SUPPLIED_EXECUTION_INPUT_SOURCE`, avoiding human round-trips and grounding execution on operative data.

---

## 4. Performance Optimization Roadmap

| Optimization | Target Area | Current Cost | Optimized Cost | Est. Runtime Savings |
| :--- | :--- | :---: | :---: | :---: |
| **1. Atomic `DRAFT_CONTRACT` in Headless Mode** | Consolidate `DRAFT_PROMPT` + `DRAFT_PLAN` | 4.30s (2 calls) | 2.50s (1 call) | **~157s (~8.1%)** |
| **2. Warm Sandbox Worker Pool** | Replace cold `python.exe` spawn with persistent pool | 1.10s / prompt | <0.05s / prompt | **~95s (~4.9%)** |
| **3. Static Prefix Prompt Caching** | Cache standard clauses & JSON schema headers | 0 tokens cached | ~2,500 cached | **~50s + 60% token cost cut** |
| **4. Streamed Sandbox Execution** | Execute Python code block while Result IR streams | Serial execution | Overlapped | **~70s (~3.6%)** |
