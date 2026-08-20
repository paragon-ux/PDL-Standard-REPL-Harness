from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

ROOT = Path(__file__).resolve().parents[1]


def _temp_harness_copy(tmp_path: Path) -> Path:
    """Copy only the logger and its tracking dependency into an isolated tree."""
    tree = tmp_path / "harness"
    (tree / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "log_live_session.py", tree / "scripts" / "log_live_session.py")
    shutil.copytree(ROOT / "tracking", tree / "tracking")
    return tree


def _fake_session(session_dir: Path) -> None:
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"workspace_path": str(session_dir / "workspaces" / "W-test")}, indent=2) + "\n",
        encoding="utf-8",
    )
    obs = session_dir / "observations"
    obs.mkdir()
    (obs / "test.jsonl").write_text(
        json.dumps(
            {
                "controller_after": {"controller_state": {"stage": "CLOSED_SUCCESS"}},
                "calls": [{"usage": {"total_tokens": 12}}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (session_dir / "transcript.log").write_text("test transcript\n", encoding="utf-8")


def test_logger_exists() -> None:
    assert (ROOT / "scripts" / "log_live_session.py").is_file()


def test_mlflow_logger_runs_isolated(tmp_path: Path) -> None:
    tree = _temp_harness_copy(tmp_path)
    session = tmp_path / "session-1"
    _fake_session(session)
    proc = subprocess.run(
        [sys.executable, str(tree / "scripts" / "log_live_session.py"), "--session-dir", str(session)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LIVE_SESSION_MLFLOW_RUN" in proc.stdout
    assert (tree / "mlflow.db").is_file(), "isolated local tracking db was not created"