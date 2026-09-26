# ADR-0007: Operationalize negative constraints by omission

- Status: Accepted
- Date: 2026-09-17
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), [ADR-0006](0006-bounded-pre-execution-reasoning.md)
- Related requirements: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md)

## Context

The controller-gated confirmation protocol enforces deliberate, inspectable decomposition:
1. Interpreting user intent into Prompt Pseudocode.
2. Deriving an inspectable Response Plan Pseudocode.
3. Executing the confirmed specification into a final deliverable.

This structure intentionally encourages thoroughness, explicit coverage of requirements, and defensive implementation. However, a structural tension arises when user prompts specify **negative constraints**—prohibitions, exclusions, and unhandled default states.

For example, when a prompt requests:
> *"Narrow exception handling only. Catch only TimeoutError and ConnectionError. Never catch broad Exception or BaseException. Ensure any other exceptions propagate immediately."*

Two opposing execution styles emerge:
- **Unconstrained baseline execution** succeeds by minimalism. It emits only the requested narrow catch block and relies on standard platform runtime behavior (e.g. unhandled exceptions propagating naturally).
- **Protocol-guided execution** often fails due to procedural over-specification. The planner attempts to make the negative instruction ("let other exceptions propagate") an explicit procedural step: `CATCH any other exception -> RAISE caught exception immediately`. When executed, this emits defensive pass-through boilerplate:
  ```python
  except Exception as e:
      raise e
  ```

While behaviorally transparent at runtime, this defensive wrapper literally introduces the prohibited pattern into the deliverable, causing automated compliance checkers to fail.

When diagnosing this tension, system designers frequently encounter several analytical pitfalls:
1. **Config-drift and tooling false alarms:** Attributing behavioral differences to runtime configuration errors or prompt drift based on incomplete inspection of execution logs.
2. **The compute-starvation trap:** Assuming that inference-time reasoning inherently causes procedural bloat, and attempting to fix the issue by stripping reasoning tokens entirely across all phases. Controlled experiments demonstrate that eliminating reasoning causes semantic collapse: models drop critical technical requirements (such as standard library module requirements) and produce English procedural prose instead of executable code.
3. **Weakening evaluation oracles:** Altering test scanners post-hoc to forgive defensive boilerplate. Loosening the evaluation oracle destroys benchmark comparability and hides real discrepancies between protocol deliverables and standard programming practices.
4. **Constrained grammar clamping:** Forcing syntactic regex masks or rigid grammars onto model outputs. This damages intermediate reasoning and violates the core protocol tenet that models must generate freely while containment is managed architecturally.

## Decision drivers

- Eliminate defensive boilerplate and negative-constraint compliance failures in deliverables.
- Preserve the protocol's deliberate, multi-stage planning benefits without proceduralizing unrequested behaviors.
- Maintain strict invariance of external evaluation suites and automated test checkers.
- Avoid over-constraining the model with rigid syntax grammars or output-distribution restrictions.
- Preserve bounded reasoning where necessary to maintain technical precision in prompt compilation.

## Decision

The protocol SHALL operationalize negative constraints, exclusions, and unhandled default conditions through **Structural Omission**, codified as normative protocol standards for planning and execution:

### 1. Operationalization by Omission
- When user instructions specify negative constraints, exclusions, or unhandled states, the Response Plan and Execution phases SHALL NOT author active procedural steps, catch-all wrappers, or redundant assertion guards (such as pass-through `except Exception: raise` blocks).
- Planning and execution SHALL rely directly on native platform runtime defaults, standard exception propagation, and programming language idioms.
- Negative constraints SHALL be satisfied by the intentional omission of prohibited constructs rather than the introduction of defensive scaffolding.

### 2. Normative Standard Clauses
This policy is enforced via standard requirements bound to the protocol stages:
- **Plan Standard (`PLAN-10`):** Requires negative constraints to be operationalized as structural omission in response plans.
- **Execution Standard (`EXEC-05`):** Prohibits the emission of defensive boilerplate, pass-through catches, or redundant assertion guards in final deliverables.

### 3. Invariance of Evaluation Oracles
- Evaluation harnesses and automated compliance scanners SHALL remain strictly immutable during system refinement.
- Protocol failures identified by automated checkers MUST be resolved by improving protocol design and normative guidance, never by weakening or retrofitting external evaluation rubrics.

### 4. Bounded Reasoning and Full Trace Grounding
- Pre-execution reasoning SHALL remain bounded rather than completely eliminated. Prompt interpretation requires sufficient inference to ground technical specifications and library dependencies, while planning and execution remain focused on procedural translation.
- Architectural investigations into unexpected model behavior MUST be validated against complete execution traces and multi-turn records, rather than speculative assumptions or partial log inspection.

## Consequences

### Positive

- **Elimination of Defensive Bloat:** Generated deliverables are idiomatic and clean, avoiding redundant try/catch layers and unnecessary pass-through wrappers.
- **Benchmark Alignment:** Protocol deliverables pass strict negative-adherence checks without requiring special exceptions or looser scoring criteria.
- **Preserved Generative Freedom:** The protocol avoids rigid grammar constraints, retaining the model's natural expressive and reasoning abilities.
- **Architectural Clarity:** Provides unambiguous guidance for future protocol developers when balancing thorough multi-step planning against minimalist negative constraints.

### Negative

- **Model Calibration:** Models must learn to distinguish between positive requirements (which require explicit procedural planning) and negative constraints (which require disciplined omission).
- **Prompt Hash Updates:** Introducing normative clauses into protocol projections alters prompt text hashes, necessitating the re-recording of automated regression fixtures.

## Alternatives considered

### Allow defensive pass-through wrappers in the evaluation scanner
Rejected. Modifying the evaluation harness to overlook pass-through exception blocks masks the underlying issue. In production, unnecessary catch-and-reraise blocks add stack noise, micro-overhead, and stylistic cruft that violate clean coding standards.

### Eliminate reasoning across all protocol stages
Rejected. While disabling reasoning can reduce verbose planning, empirical evaluations show it degrades prompt interpretation on technical tasks, causing models to drop standard library dependencies and output procedural descriptions instead of working code.

### Enforce grammar constraints on execution output
Rejected. Constraining outputs via grammar engines or regex parsers restricts expressive power and often induces loops or failures when tasks require flexible, multi-paradigm solutions.
