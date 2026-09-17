from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

# Recorded fixtures are externalized (repo-restructure-plan §3.1):
# PDLT_FIXTURES_PATH env override -> repo-relative vendored location.
FIXTURES_DIR = Path(
    os.environ.get("PDLT_FIXTURES_PATH", str(ROOT / "fixtures" / "r4-recorded-worker"))
)


def _fixture() -> dict:
    return json.loads((FIXTURES_DIR / "recorded-cases.json").read_text(encoding="utf-8"))


def test_required_runtime_files_exist() -> None:
    required = (
        "scripts/runtime/session_engine.py",
        "scripts/runtime/workspace.py",
        "scripts/runtime/normative_store.py",
        "scripts/controller/mechanical_controller.py",
        "contracts/EXECUTION_CONTRACT.json",
        "scripts/host/repl.py",
        "scripts/providers/fixtures.py",
        "README.md",
        "SOURCE_PROVENANCE.json",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_zero_template_workspace_invariant() -> None:
    """S2 / ADR-0008: the physical workspace template must be gone."""
    assert not (ROOT / "workspace-template").exists()


def test_no_absolute_source_repo_paths() -> None:
    _src = "PDL-Standard-R2S"
    markers = ("Desktop" + "\\Frameworks\\" + _src, "Desktop" + "/Frameworks/" + _src)
    ignored_dirs = {".git", "runs", "mlruns", ".pytest_cache", ".venv", "venv", "scratch"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored_dirs for part in path.parts):
            continue
        if path.name == "SOURCE_PROVENANCE.json":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            assert marker not in text, f"{path}:{marker}"


def test_fresh_workspace_lifecycle_and_resume(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from scripts.host.app import PDLtHost
    from scripts.providers.fixtures import build_recorded_fixture_from_vendored

    fixture_file = FIXTURES_DIR / "recorded-cases.json"
    fixture = _fixture()
    turns = fixture["case_turns"]["G06"]
    worker = build_recorded_fixture_from_vendored(ROOT, fixture_file, case_ids=["G06"])
    host = PDLtHost(
        ROOT,
        worker=worker,
        workspace_root=tmp_path / "workspaces",
        run_id="test",
        observation_dir=tmp_path / "observations",
    ).start()
    try:
        for turn in turns:
            host.handle(turn)
        status = host.status()
        workspace_path = Path(status["workspace_path"])
        assert (status.get("controller_state") or {}).get("stage") == "CLOSED_SUCCESS"
        from scripts.runtime.workspace import WorkspaceRun as _WR
        _stages = _WR.open(ROOT, workspace_path).stages_root()
        assert (_stages / "50_execution" / "output" / "current.json").is_file()
    finally:
        host.close()

    worker2 = build_recorded_fixture_from_vendored(ROOT, fixture_file, case_ids=["G06"])
    resumed = PDLtHost(
        ROOT,
        worker=worker2,
        restore_path=workspace_path,
        run_id="test-resume",
        observation_dir=tmp_path / "observations-resume",
    ).start()
    try:
        assert (resumed.status().get("controller_state") or {}).get("stage") == "CLOSED_SUCCESS"
    finally:
        resumed.close()


def test_worker_substitution_live_stub(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from scripts.host.app import PDLtHost
    from scripts.providers.live_stub import LiveStubWorker

    host = PDLtHost(
        ROOT,
        worker=LiveStubWorker(),
        workspace_root=tmp_path / "workspaces",
        run_id="stub",
        observation_dir=tmp_path / "observations",
    ).start()
    try:
        host.handle("Use $confirm-with-pseudocode to explain version control.")
        host.handle("This is correct.")
        host.handle("Confirm the plan and execute.")
        stage = (host.status().get("controller_state") or {}).get("stage")
        assert stage == "CLOSED_SUCCESS"
    finally:
        host.close()


def test_vendored_fixture_matches_source_manifest() -> None:
    manifest = json.loads((FIXTURES_DIR / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    fixture = _fixture()
    by_source = {entry["source_evidence_run"]: entry["prompt_sha256"] for entry in manifest.get("entries", [])}
    for entry in fixture["entries"]:
        expected = by_source.get(entry["source"])
        if expected is not None:
            assert entry["prompt_sha256"] == expected