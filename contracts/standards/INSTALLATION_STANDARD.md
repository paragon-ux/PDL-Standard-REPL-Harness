# Installation Standard

Normative scope: mechanical identity and integrity of an installable contract/runtime package.

**INSTALL-01 — Manifested package.** The installable package MUST have a machine-readable manifest identifying its installation unit and declared files.

**INSTALL-02 — Recursive integrity.** Required subdirectories and files MUST be installed recursively rather than assuming a single entrypoint file is sufficient.

**INSTALL-03 — Declared identity.** Each required runtime file MUST have a declared content digest using the manifest's stated algorithm and normalization rule.

**INSTALL-04 — Exact file set.** When exact-tree mode is enabled, undeclared substantive runtime files and missing declared files MUST fail mechanical verification.

**INSTALL-05 — Safe paths.** Manifest paths MUST be relative, traversal-safe, and unique.

**INSTALL-06 — Source/install equivalence.** The same manifest MUST be usable to verify reviewed source bytes and installed package bytes.

**INSTALL-07 — Mechanical-only verifier.** Installation verification MUST NOT claim to verify Prompt semantics, Plan semantics, review meaning, execution fidelity, evidence quality, or model reasoning.
