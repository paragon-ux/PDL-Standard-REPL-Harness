"""Unit tests for Option 3: MemoryWorkspaceRun in-memory caching & turn archive flushing."""

from __future__ import annotations

from pathlib import Path
import json

from pdl_taskmaster.runtime.workspace import MemoryWorkspaceRun, WorkspaceRun

ROOT = Path(__file__).resolve().parents[1]


def test_memory_workspace_reads_from_vfs(tmp_path: Path):
    """MemoryWorkspaceRun reads directly from RAM VFS buffer."""
    ws = MemoryWorkspaceRun.create(ROOT, tmp_path / "workspaces", turn_id="turn_001")
    ws.publish_execution_outcome("RESULT", "test execution output", {"meta_key": "val"})

    meta, body = ws.read_artifact("result")
    assert body == "test execution output"
    assert meta["kind"] == "RESULT"
    assert meta["meta_key"] == "val"


def test_memory_workspace_turn_archive_flush(tmp_path: Path):
    """Closing a turn flushes turn_archive.json and state to disk."""
    ws = MemoryWorkspaceRun.create(ROOT, tmp_path / "workspaces", turn_id="turn_001")
    ws.publish_execution_outcome("RESULT", "final code deliverable")
    archive = ws.flush_turn_archive()

    assert archive.is_file()
    data = json.loads(archive.read_text(encoding="utf-8"))
    assert data["turn_id"] == "turn_001"
    assert "events" in data
    assert "flushed_at_utc" in data
