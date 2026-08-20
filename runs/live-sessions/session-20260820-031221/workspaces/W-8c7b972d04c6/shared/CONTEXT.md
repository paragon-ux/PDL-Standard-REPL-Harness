# Shared run state

Layer 4 shared working state that is explicitly authorized across stages.

The runtime uses this area for ordered, opaque source messages that contain confirmed
approach semantics. It does not ask semantic workers to reproduce those messages into a
second payload. Controller state is persisted separately under `state/`; event history is
persisted under `events/`. No file in this directory independently defines protocol correctness.
