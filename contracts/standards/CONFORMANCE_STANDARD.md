# Conformance Standard

Normative scope: classes and authority limits of protocol verification.

**CONFORM-01 — Mechanical checks.** An `M` check may conclusively establish only mechanically decidable facts over machine-addressable inputs, such as existence, identity, digest, version, state, count, or allowed transition.

**CONFORM-02 — Semantic checks.** An `S` check may evaluate semantic conformance to referenced Standard requirements but MUST NOT create or change user intent or confirmed task semantics.

**CONFORM-03 — Human checks.** An `H` check is explicit user confirmation or review that establishes semantic disposition where the protocol assigns that authority to the user.

**CONFORM-04 — Requirement traceability.** Every verification check MUST reference one or more existing Standard requirement IDs. A check without a corresponding Standard requirement is invalid.

**CONFORM-05 — No silent omission.** A Standard requirement that cannot be mechanically proven MUST NOT be silently treated as mechanically verified; it must be classified as `S`, `H`, or explicitly non-applicable for the operation.

**CONFORM-06 — Failed validation does not advance.** A failed required validation MUST NOT advance protocol state.
