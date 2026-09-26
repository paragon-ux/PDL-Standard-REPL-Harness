from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
ROOT = Path(__file__).resolve().parents[2]

# Recorded fixtures are externalized (repo-restructure-plan §3.1):
# PDLT_FIXTURES_PATH env override -> repo-relative vendored location -> sibling PDL-Standard-Archive.
def _resolve_fixture_file() -> Path:
    env = os.environ.get("PDLT_FIXTURES_PATH", "").strip()
    if env:
        return Path(env) / "recorded-cases.json"
    local = ROOT / "fixtures" / "r4-recorded-worker" / "recorded-cases.json"
    if local.is_file():
        return local
    archive = ROOT.parent / "PDL-Standard-Archive" / "fixtures-r4-recorded-worker" / "recorded-cases.json"
    if archive.is_file():
        return archive
    return local

FIXTURE = _resolve_fixture_file()

mlflow = pytest.importorskip("mlflow")


def _g06_turns() -> list[str]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return fixture["case_turns"]["G06"]


def _run_repl(tmp_path: Path, lines: list[str], session_id: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "scripts.host.repl",
        "--candidate-repo",
        str(ROOT),
        "--worker",
        "recorded",
        "--evidence",
        str(FIXTURE),
        "--case-ids",
        "G06",
        "--workspace-root",
        str(tmp_path / "sessions"),
        "--session-id",
        session_id,
    ]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_repl_command_loop_full_deterministic_session(tmp_path: Path) -> None:
    turns = _g06_turns()
    lines = (
        turns
        + ["/status", "/help", "/session", "/mlflow on", "/worker recorded", "/new"]
        + turns
        + ["/status", "/resume repltest", "/status", "/quit"]
    )
    mlflow_db = ROOT / "mlflow.db"
    db_existed = mlflow_db.exists()
    proc = _run_repl(tmp_path, lines, "repltest")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "PDLt REPL started" in out
    assert "/status -> read-only host state" in out
    assert "worker switched to recorded" in out
    assert "new session:" in out
    assert "resumed session:" in out
    assert out.count("[protocol closed]") >= 2
    assert out.count("CLOSED_SUCCESS") >= 3
    assert out.count("LIVE_SESSION_MLFLOW_RUN") >= 3  # worker switch, /new, and exit/resume logging
    assert "No such file" not in out
    assert "Traceback" not in out
    # First session completed -> durable session pointer exists.
    assert (tmp_path / "sessions" / "repltest" / "session.json").is_file()
    if not db_existed and mlflow_db.exists():
        mlflow_db.unlink()


def test_new_session_is_lazy_no_fabricated_workspace(tmp_path: Path) -> None:
    proc = _run_repl(tmp_path, ["/new", "/quit"], "lazytest")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    match = re.search(r"new session: (\S+)", out)
    assert match is not None, out
    new_dir = Path(match.group(1))
    assert new_dir.is_dir()
    assert not (new_dir / "session.json").exists(), "pointer must be written lazily after first turn"
    assert not list(new_dir.glob("workspaces/W-*")), "no workspace should be fabricated before a turn"


def test_repl_headless_exit_fail_closed_on_unconfirmed_stage(tmp_path: Path) -> None:
    """ADR-0012 / Kimi pushback: non-interactive runs halting at an unconfirmed stage must exit code 2."""
    turns = _g06_turns()
    # Sending only turn 1 halts at PROMPT_REVIEW_WAIT (unconfirmed review gate)
    proc = _run_repl(tmp_path, turns[:1], "headless_unconfirmed")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 2, out[-2000:]
    assert "[headless halt] Session ended at non-terminal stage" in proc.stderr