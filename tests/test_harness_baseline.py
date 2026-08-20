from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> dict:
    return json.loads((ROOT / "fixtures" / "r4-recorded-worker" / "recorded-cases.json").read_text(encoding="utf-8"))


def test_required_runtime_files_exist() -> None:
    required = (
        "runtime/session_engine.py",
        "runtime/workspace.py",
        "controller/mechanical_controller.py",
        "contracts/EXECUTION_CONTRACT.json",
        "workspace-template/stages/50_execution/CONTEXT.md",
        "host/repl.py",
        "providers/fixtures.py",
        "fixtures/r4-recorded-worker/recorded-cases.json",
        "README.md",
        "SOURCE_PROVENANCE.json",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_no_absolute_source_repo_paths() -> None:
    markers = ("Desktop\\Frameworks\\PDL-Standard-R2S", "Desktop/Frameworks/PDL-Standard-R2S")
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            assert marker not in text, f"{path}:{marker}"


def test_fresh_workspace_lifecycle_and_resume(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from host.app import PDLtHost
    from providers.fixtures import build_recorded_fixture_from_vendored

    fixture_file = ROOT / "fixtures" / "r4-recorded-worker" / "recorded-cases.json"
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
        assert (workspace_path / "stages" / "50_execution" / "output" / "current.json").is_file()
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
    from host.app import PDLtHost
    from providers.live_stub import LiveStubWorker

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
    manifest = json.loads((ROOT / "fixtures" / "r4-recorded-worker" / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    fixture = _fixture()
    by_source = {entry["source_evidence_run"]: entry["prompt_sha256"] for entry in manifest.get("entries", [])}
    for entry in fixture["entries"]:
        expected = by_source.get(entry["source"])
        if expected is not None:
            assert entry["prompt_sha256"] == expected