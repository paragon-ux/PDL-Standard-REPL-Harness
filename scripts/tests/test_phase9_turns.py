"""Phase 9 (v2.4.0) tests: S3 turn-directory hierarchy and S4 deliverable chaining.

S3: WorkspaceRun supports an optional turn-scoped layout
(turns/<turn_id>/{state,events,stages}) while the legacy flat layout remains
byte-identical for single-turn runners and recorded fixtures.

S4: the prior turn's confirmed deliverable is the only artifact that crosses
the turn boundary; drafts, rejected plans, and review dialogue are
structurally unreachable in the new turn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime.workspace import WorkspaceError, WorkspaceRun  # noqa: E402


def test_legacy_flat_layout_unchanged(tmp_path: Path) -> None:
    """Backwards compatibility: no turn_id -> exactly the pre-Phase-9 layout."""
    ws = WorkspaceRun.create(ROOT, tmp_path)
    assert (ws.path / "state").is_dir()
    assert (ws.path / "events").is_dir()
    assert (ws.path / "stages").is_dir()
    assert (ws.path / "shared").is_dir()
    assert not (ws.path / "turns").exists()
    assert ws.turn_id is None
    # controller state + invocation counter stay at the workspace root
    assert ws.controller_state_path == ws.path / "state" / "controller-state.json"
    inv = ws.materialize_operation("BOOTSTRAP_ANALYSIS", {"HOST_PROTOCOL_STATE": "X", "RAW_UNTRUSTED_CONTENT": "y"})
    assert str(inv.input_dir).startswith(str(ws.path / "stages"))
    # bind_protocol rebinding stays forbidden in flat mode
    ws.bind_protocol("instance-1")
    with pytest.raises(WorkspaceError):
        ws.bind_protocol("instance-2")


def test_turn_hierarchy_scaffold_and_routing(tmp_path: Path) -> None:
    """S3: turn-scoped state/events/stages under turns/<turn_id>/."""
    ws = WorkspaceRun.create(ROOT, tmp_path, turn_id="turn_001")
    assert ws.turn_id == "turn_001"
    # session-level dirs at root; stage tree scoped to the turn
    assert (ws.path / "shared").is_dir()
    assert (ws.path / "turns" / "turn_001" / "state").is_dir()
    assert (ws.path / "turns" / "turn_001" / "events").is_dir()
    assert (ws.path / "turns" / "turn_001" / "stages").is_dir()
    assert not (ws.path / "stages").exists()
    turn_meta = ws.read_turn_status("turn_001")
    assert turn_meta["status"] == "ACTIVE"

    # stage materialization and controller state route through the turn scope
    assert ws.controller_state_path == ws.path / "turns" / "turn_001" / "state" / "controller-state.json"
    inv = ws.materialize_operation("BOOTSTRAP_ANALYSIS", {"HOST_PROTOCOL_STATE": "X", "RAW_UNTRUSTED_CONTENT": "y"})
    assert str(inv.input_dir).startswith(str(ws.path / "turns" / "turn_001" / "stages"))
    # events are turn-scoped
    assert (ws.path / "turns" / "turn_001" / "events" / "events.jsonl").is_file()


def test_start_turn_moves_pointer_and_preserves_history(tmp_path: Path) -> None:
    ws = WorkspaceRun.create(ROOT, tmp_path, turn_id="turn_001")
    ws.publish_execution_outcome("RESULT", "first deliverable body")
    first_events = ws.path / "turns" / "turn_001" / "events" / "events.jsonl"
    before = first_events.read_text(encoding="utf-8")

    ws.start_turn("turn_002")
    assert ws.turn_id == "turn_002"
    assert (ws.path / "turns" / "turn_002" / "stages").is_dir()
    assert not (ws.path / "turns" / "turn_002" / "stages" / "50_execution").exists()
    # prior turn state preserved verbatim
    assert first_events.read_text(encoding="utf-8") == before
    with pytest.raises(WorkspaceError):
        ws.start_turn("turn_002")  # pointer unchanged
    assert ws.next_turn_id() == "turn_003"


def test_previous_deliverable_returns_only_confirmed_success_turn(tmp_path: Path) -> None:
    """S4: the prior deliverable is the ONLY thing reachable across turns."""
    ws = WorkspaceRun.create(ROOT, tmp_path, turn_id="turn_001")
    assert ws.previous_deliverable() is None  # nothing closed yet
    ws.publish_execution_outcome("RESULT", "confirmed deliverable one")
    ws.mark_turn_status("CLOSED_SUCCESS", deliverable_sha256="abc123")

    ws.start_turn("turn_002")
    assert ws.previous_deliverable() == "confirmed deliverable one"

    # drafts from the *current* turn are unreachable as previous deliverables
    ws.publish_execution_outcome("RESULT", "turn two draft")
    assert ws.previous_deliverable() == "confirmed deliverable one"

    # a cancelled prior turn never becomes a previous deliverable
    ws.mark_turn_status("CLOSED_CANCELLED")
    ws.start_turn("turn_003")
    assert ws.previous_deliverable() == "confirmed deliverable one"


def test_per_turn_protocol_binding(tmp_path: Path) -> None:
    """Each turn runs its own protocol lifecycle; rebinding across turns is expected."""
    ws = WorkspaceRun.create(ROOT, tmp_path, turn_id="turn_001")
    ws.bind_protocol("instance-one")
    assert ws.read_turn_status("turn_001")["protocol_instance_id"] == "instance-one"
    ws.start_turn("turn_002")
    ws.bind_protocol("instance-two")  # must not raise in hierarchy mode
    assert ws.read_turn_status("turn_002")["protocol_instance_id"] == "instance-two"


def test_engine_chaining_compiles_previous_deliverable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S4 engine path: after a CLOSED_SUCCESS turn, a new message chains into
    the next turn with the prior deliverable compiled as background context."""
    from scripts.host.app import PDLtHost
    from scripts.providers.live_stub import LiveStubWorker
    from scripts.runtime.operation_bridge import ModelRequest

    captured: list[dict] = []

    class CapturingStub(LiveStubWorker):
        def call(self, request: ModelRequest):
            if request.operation == "BOOTSTRAP_ANALYSIS":
                captured.append(request.prompt)
            return super().call(request)

    host = PDLtHost(
        ROOT,
        worker=CapturingStub(),
        workspace_root=tmp_path / "workspaces",
        run_id="phase9-chain",
        render_compact=True,
    ).start()
    try:
        first = host.handle("Draft a short apology note about a broken heater.")
        assert not first.closed
        # drive through the gates with stub confirmations
        steps = 0
        while not first.closed and steps < 8:
            steps += 1
            st = (host.status().get("controller_state") or {}).get("stage")
            if st in {"PROMPT_REVIEW", "PLAN_REVIEW"}:
                first = host.handle("Confirm.")
            elif st == "WAITING_INPUT":
                first = host.handle("Proceed with execution.")
            elif st in {"CLOSED_SUCCESS", "CLOSED_CANCELLED"}:
                break
            else:
                first = host.handle("Confirm.")
        assert first.closed, "first turn did not close"

        captured.clear()
        second = host.handle("Now draft a thank-you note for the same landlord.")
        assert not second.bypass
        ws_path = Path(host.status()["workspace_path"])
        ws = WorkspaceRun.open(ROOT, ws_path)
        assert ws.turn_id == "turn_002"
        assert ws.previous_deliverable() is not None
        # the chained bootstrap projection carries the prior deliverable
        assert captured, "no bootstrap call captured in turn 2"
        assert "PREVIOUS_DELIVERABLE" in captured[0]
    finally:
        host.close()
