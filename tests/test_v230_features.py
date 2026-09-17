"""Unit tests for PDLt Version 2.3.0 features and fixes:
- NormativeStore resolution & zero-template dynamic WorkspaceRun (ADR-0008)
- Model classification Class B thinking token budgets & ApiWorker serialization
- Review stage silence-deferral bug fix & fast-path review actions (/confirm, /revise, /stop)
- Verification contract synchronization
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.normative_store import NormativeStore
from runtime.workspace import WorkspaceRun
from runtime.model_classification import get_proportional_reasoning_mapping
from providers.api_worker import ApiWorker
from controller.mechanical_controller import Intent, Stage, ProtocolState


def test_normative_store_resolution(tmp_path: Path):
    # Pinned version file resolution
    pin_file = tmp_path / ".pdlt-version"
    pin_file.write_text("v2.5", encoding="utf-8")
    assert NormativeStore.resolve_version(tmp_path) == "v2.5"

    # Default fallback to repo contracts
    standards_root = NormativeStore.resolve_standards_root(ROOT)
    assert standards_root.is_dir()
    assert (standards_root / "CONTRACT_MANIFEST.json").is_file()

    contract = NormativeStore.resolve_contract(ROOT, "EXECUTION_CONTRACT.json")
    assert contract.is_file()

    # Explicit PDLT_STANDARDS_PATH override
    import os
    override_dir = tmp_path / "custom_standards"
    override_dir.mkdir()
    (override_dir / "CONTRACT_MANIFEST.json").write_text("{}", encoding="utf-8")
    os.environ["PDLT_STANDARDS_PATH"] = str(override_dir)
    try:
        assert NormativeStore.resolve_standards_root(ROOT) == override_dir
    finally:
        del os.environ["PDLT_STANDARDS_PATH"]


def test_zero_template_dynamic_workspace(tmp_path: Path):
    # Creating a workspace should not copy 35 static files from template
    ws = WorkspaceRun.create(ROOT, tmp_path)
    assert ws.path.is_dir()
    assert (ws.path / "workspace.json").is_file()

    # Verify no template bloat initially
    files_created = list(ws.path.glob("**/*"))
    # Inodes should be minimal (state, events, stages, shared, workspace.json)
    assert len(files_created) <= 8

    # Dynamic stage creation on demand
    stage = ws._stage_for("DRAFT_PROMPT", {})
    assert stage == "10_prompt"
    assert (ws.path / "stages" / "10_prompt").is_dir()


def test_class_b_model_classification_and_api_worker():
    # Class B Claude returns explicit token budgets
    claude_mapping = get_proportional_reasoning_mapping("anthropic/claude-3.5-sonnet")
    assert claude_mapping["BOOTSTRAP_ANALYSIS"] == 4096
    assert claude_mapping["DRAFT_PROMPT"] == 1024
    assert claude_mapping["EXECUTE"] == "none"

    # ApiWorker initializes with proportional reasoning mapping by default
    worker = ApiWorker(
        model="anthropic/claude-3.5-sonnet",
        repo_root=ROOT,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="TEST_KEY",
    )
    assert worker._reasoning_for("BOOTSTRAP_ANALYSIS") == 4096
    assert worker._reasoning_for("DRAFT_PROMPT") == 1024
    assert worker._reasoning_for("EXECUTE") == "none"


def test_verification_contract_contains_v230_standards():
    contract_path = ROOT / "contracts" / "VERIFICATION_CONTRACT.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))

    v_plan_s = next(c for c in data["checks"] if c["id"] == "V-PLAN-S")
    assert "PLAN-09" in v_plan_s["requirements"]
    assert "PLAN-10" in v_plan_s["requirements"]

    v_exec_s = next(c for c in data["checks"] if c["id"] == "V-EXEC-S")
    assert "EXEC-04" in v_exec_s["requirements"]
    assert "EXEC-05" in v_exec_s["requirements"]


def test_silence_deferral_and_fast_paths_in_session_engine(tmp_path: Path):
    from runtime.session_engine import SessionEngine
    from controller.mechanical_controller import Artifact, AtomicJsonStore, MechanicalController

    engine = SessionEngine(
        ROOT,
        lambda req: '{"kind": "ANALYSIS", "task_summary": "Clean task", "approach_notes": "", "risk_notes": "", "task_entities": []}',
        workspace_root=tmp_path,
    )
    ws = WorkspaceRun.create(ROOT, tmp_path)
    state = ProtocolState.new()
    state.stage = Stage.PROMPT_REVIEW
    prompt_id = f"{state.instance_id}-P1"
    prompt_body = "PROMPT\nTASK: test\nEND"
    state.prompt_highwater = 1
    state.current_prompt = Artifact(prompt_id, prompt_body, confirmed=False)
    ws.publish_artifact("prompt", prompt_id, prompt_body, confirmed=False)
    ws.publish_approach_sources([])
    ws.bind_protocol(state.instance_id)
    engine.workspace = ws
    engine.controller = MechanicalController(state, AtomicJsonStore(ws.controller_state_path))

    # Test Silence Deferral fix: empty/whitespace input prompts for confirmation
    resp = engine.handle_user_message("   ")
    assert "Please confirm" in resp.text
    assert "/confirm" in resp.text

    # Test /confirm fast-path (transitions to DRAFT_PLAN without calling LLM review parser)
    def mock_model(req):
        if req.operation == "BOOTSTRAP_ANALYSIS":
            return '{"kind": "ANALYSIS", "task_summary": "Clean task", "approach_notes": "", "risk_notes": "", "task_entities": []}'
        if req.operation in {"DRAFT_PLAN", "REVISE_PLAN"}:
            return '{"neutral_plan_body": "PLAN\\nSTEP 1: revised step\\nEND"}'
        return '{"neutral_plan_body": "PLAN\\nSTEP 1: clean step\\nEND"}'

    engine.model_call = mock_model
    resp2 = engine.handle_user_message("/confirm")
    assert engine.controller.state.stage == Stage.PLAN_REVIEW

    # Test empty /revise prompts for feedback
    resp3 = engine.handle_user_message("/revise")
    assert "Please specify your revisions" in resp3.text

    # Test /revise <feedback> fast-path in PLAN_REVIEW
    resp4 = engine.handle_user_message("/revise please use async httpx")
    assert engine.controller.state.stage == Stage.PLAN_REVIEW
    assert "revised step" in resp4.text

    # Test /stop fast-path
    resp5 = engine.handle_user_message("/stop")
    assert resp5.closed is True
    assert engine.controller.state.stage == Stage.CLOSED_CANCELLED
