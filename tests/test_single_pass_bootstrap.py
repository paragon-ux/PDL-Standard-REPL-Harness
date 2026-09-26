"""Unit tests for Option 1: Single-Pass Interactive Ingestion Optimization."""

from __future__ import annotations

from pathlib import Path
import json
import pytest

from pdl_taskmaster.runtime.operation_bridge import ModelRequest
from pdl_taskmaster.runtime.session_engine import SessionEngine

ROOT = Path(__file__).resolve().parents[1]


def test_single_pass_bootstrap_bypasses_bootstrap_analysis(tmp_path: Path):
    """When single_pass_bootstrap=True, Turn 1 bypasses BOOTSTRAP_ANALYSIS and dispatches directly to DRAFT_PROMPT."""
    calls: list[str] = []

    def mock_model(request: ModelRequest) -> str:
        calls.append(request.operation)
        if request.operation == "INTERPRET_ACTIVATION":
            return json.dumps({"route": "APPLY_PROTOCOL"})
        if request.operation == "DRAFT_PROMPT":
            return json.dumps({
                "kind": "PROMPT",
                "prompt_body": "def task(): pass",
                "approach_handoff": "NONE",
                "task_entities": ["task"],
            })
        raise ValueError(f"unexpected op: {request.operation}")

    engine = SessionEngine(
        ROOT,
        model_call=mock_model,
        workspace_root=tmp_path / "workspaces",
        single_pass_bootstrap=True,
    )
    engine.workspace = engine._new_workspace()

    resp = engine.handle_user_message("Create a simple task runner")
    assert resp.closed is False
    assert resp.text is not None
    # BOOTSTRAP_ANALYSIS should NOT have been called
    assert "BOOTSTRAP_ANALYSIS" not in calls
    # Exactly INTERPRET_ACTIVATION and DRAFT_PROMPT occurred
    assert calls == ["INTERPRET_ACTIVATION", "DRAFT_PROMPT"]
    assert engine.controller is not None
    assert engine.controller.state.current_prompt is not None


def test_two_pass_bootstrap_preserves_bootstrap_analysis(tmp_path: Path):
    """When single_pass_bootstrap=False, Turn 1 executes the standard two-pass BOOTSTRAP_ANALYSIS -> DRAFT_PROMPT."""
    calls: list[str] = []

    def mock_model(request: ModelRequest) -> str:
        calls.append(request.operation)
        if request.operation == "INTERPRET_ACTIVATION":
            return json.dumps({"route": "APPLY_PROTOCOL"})
        if request.operation == "BOOTSTRAP_ANALYSIS":
            return json.dumps({
                "kind": "ANALYSIS",
                "task_summary": "Task summary for runner with task entity",
                "approach_notes": "Procedural guidance",
                "risk_notes": "None",
                "task_entities": ["task"],
            })
        if request.operation == "DRAFT_PROMPT":
            return json.dumps({
                "kind": "PROMPT",
                "prompt_body": "def task(): pass",
                "approach_handoff": "NONE",
                "task_entities": ["task"],
            })
        raise ValueError(f"unexpected op: {request.operation}")

    engine = SessionEngine(
        ROOT,
        model_call=mock_model,
        workspace_root=tmp_path / "workspaces",
        single_pass_bootstrap=False,
    )
    engine.workspace = engine._new_workspace()

    resp = engine.handle_user_message("Create a simple task runner")
    assert resp.closed is False
    # BOOTSTRAP_ANALYSIS must be called after activation, then DRAFT_PROMPT
    assert calls == ["INTERPRET_ACTIVATION", "BOOTSTRAP_ANALYSIS", "DRAFT_PROMPT"]
