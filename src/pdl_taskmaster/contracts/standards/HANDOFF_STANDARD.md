# Handoff Standard

Normative scope: mechanically checkable artifact/state invariants between operations.

**HANDOFF-01 — Instance binding.** Artifacts committed to an active protocol lifecycle MUST be mechanically bound to that host-owned instance.

**HANDOFF-02 — Current artifact tracking.** The host MUST maintain the mechanically current Prompt and Plan artifact identities and versions.

**HANDOFF-03 — Confirmation version binding.** Confirmation MUST bind to the mechanically current displayed artifact version; stale or state-incompatible confirmation events MUST NOT advance the protocol.

**HANDOFF-04 — Confirmed immutability.** Confirmed artifact content MUST be immutable. Revision MUST create a new current version rather than mutate a confirmed version in place.

**HANDOFF-05 — Plan provenance.** A current Plan MUST record the current Prompt version from which it was generated. A Plan whose source Prompt is no longer current MUST NOT authorize execution.

**HANDOFF-06 — Prompt-revision invalidation.** A `TASK-01` Prompt revision MUST invalidate the superseded Prompt confirmation and any Plan derived from the superseded Prompt.

**HANDOFF-07 — Failed-generation preservation.** Failure to generate or validate a replacement artifact MUST NOT discard or mutate the previously committed current artifact state.

**HANDOFF-08 — Replay protection.** A persisted externally visible action whose outcome is not recorded MUST NOT be silently replayed after restore; outcome uncertainty MUST be preserved until resolved.

**HANDOFF-09 — Approach-projection preservation.** Host state MUST preserve the ordered `TASK-02` projections produced from operative user input during an active instance and MUST make them available to later Plan generation or revision. Preserving those projections MUST NOT by itself alter Prompt artifact content or Prompt confirmation state.
