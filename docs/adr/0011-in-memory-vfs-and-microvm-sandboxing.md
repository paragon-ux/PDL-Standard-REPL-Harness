# ADR-0011: Software-Defined In-Memory VFS and Ephemeral MicroVM Sandboxing

- Status: Accepted
- Date: 2026-09-26
- Parent decision: [ADR-0001](0001-controller-gated-pseudocode-protocol.md)
- Related decisions: [ADR-0004](0004-confirmed-artifacts-as-execution-boundary.md), [ADR-0008](0008-context-and-session-management.md), [ADR-0010](0010-pydantic-wire-enforcement.md)
- Related requirements: [TRD-0002](../trd/0002-controller-gated-pseudocode-protocol.md)

## Context

The Inter-Process Context Management (ICM) substrate in `WorkspaceRun` was designed to guarantee immutable stage isolation, byte-reproducible inspection, and offline replayability. Under ADR-0008, dynamic materialization reduced template duplication, but the operational substrate remained physically tied to disk.

In real-world deployment—particularly on Windows NTFS—this physical filesystem-backed model created a critical operational bottleneck:
1. **Severe I/O Latency:** Every operation invocation materializes input and output directories and writes multiple serialized symbols (`index.json`, `invocation.json`, `compiled-projection.json`, `model-response.txt`, `invocation-counter.json`, event logs). Each file write executes `tempfile.mkstemp()` followed by `os.fsync()`. In a 5-stage lifecycle turn, 60 to 100 synchronous `os.fsync()` calls occur, adding 1.5 to 4 seconds of blocking disk metadata journaling per turn.
2. **Storage and Inode Proliferation:** Across multi-turn sessions and comprehensive evaluation batteries (e.g. the 162-trial F6.3 adversarial suite), the harness generated over 87,000 physical files, exhausting file handles, straining OS directory walkers, and necessitating emergency compaction hacks (Decision D22).
3. **Execution Plane Security Deficit:** Running untrusted or model-generated code during the `EXECUTE` stage on the bare host filesystem presents severe breakout risks, while traditional shared-kernel Docker containers introduce volume mount translation latency (VirtioFS/9p) and container escape vulnerabilities.

## Decision drivers

- Eliminate the multi-second filesystem I/O bottleneck and `os.fsync()` latency on Windows NTFS during active protocol execution.
- Maintain the ICM invariants: strict content-addressed stage isolation, verifiable handoffs, and deterministic replayability.
- Prevent physical disk bloat by eliminating the creation of thousands of transient stage files on the host filesystem.
- Provide hardware-level, ephemeral compute sandboxing for code and tool execution without shared-kernel container risks.
- Enforce strict capability boundaries using the Model Context Protocol (MCP).

## Decision

The harness SHALL decouple the **Context Flow Data Plane** from host disk storage by adopting an **In-Memory Virtual Filesystem (VFS)** for active turns, and encapsulate the **Compute Execution Plane** within **Ephemeral MicroVM Sandboxes**:

### 1. In-Memory Virtual Filesystem (`MemoryWorkspaceRun`)
- Active session stages, input/output symbols, projections, and telemetry events SHALL materialize in memory using a high-performance in-memory VFS (dict/RAM buffers) rather than physical disk directories.
- `WorkspaceRun` interfaces (`materialize_operation`, `record_projection`, `publish_artifact`, `append_event`) execute in sub-millisecond RAM operations, bypassing all `os.fsync()` and NTFS metadata journaling.
- Replay deterministic hashing (`sha256`) is computed directly from in-memory byte buffers.

### 2. Atomic Turn Flush and Single-Artifact Persistence
- The harness SHALL NOT write individual loose files for intermediate stage steps.
- Persistence to host storage occurs strictly upon task epoch completion (`CLOSED_SUCCESS` or `CLOSED_CANCELLED`):
  - Completed turns are serialized to a single compact SQLite record or single compressed session archive (`.tar.zst` or `.jsonl` stream).
  - Individual stage trees are retained only when explicitly requested via `--debug-preserve-workspaces`.

### 3. Ephemeral MicroVM-Backed Agentic Sandboxing
- Execution of untrusted code, external tools, and terminal deliverables during the `EXECUTE` stage SHALL NOT run on bare metal.
- The execution plane SHALL run within an ephemeral MicroVM sandbox (e.g. Firecracker, E2B, or Docker Cloud Sandbox):
  - **Copy-on-Write (CoW) Snapshots:** Sandboxes boot from pre-warmed memory snapshots in $<50\text{ms}$.
  - **RAM-Backed OverlayFS:** Scratchpad file modifications occur entirely in temporary memory overlays.
  - **Zero-Remnant Teardown:** Upon deliverable extraction, the sandbox snapshot is discarded, leaving zero disk artifacts on the host.

### 4. Model Context Protocol (MCP) as the Capability Boundary
- Sandboxed agents SHALL NOT be granted direct socket access or host network bridging.
- All file reads, linting checks, and tool invocations must route through authenticated, typed **MCP endpoints** monitored by the host `SessionEngine`.
- Any tool call or file modification outside the confirmed `ExecutionContract` is mechanically rejected at the MCP bridge.

## Consequences

### Positive
- Drops workspace context handoff latency from **1,500–4,000ms down to $<5\text{ms}$** per turn on Windows NTFS.
- Eliminates the generation of tens of thousands of loose files, permanently solving inode exhaustion and directory traversal bottlenecks.
- Isolates untrusted code execution inside hardware-virtualized MicroVMs with zero persistence and zero host escape risk.

### Neutral / Negative
- Requires maintaining an in-memory VFS abstraction alongside optional disk serialization for test inspection.
- Ephemeral MicroVM sandboxing requires a local runtime backend (e.g. WSL2/E2B/Docker Desktop) or remote cloud sandbox provider for live execution trials.
