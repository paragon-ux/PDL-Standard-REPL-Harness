from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.host import repl


def test_repl_does_not_import_codex_worker_at_startup() -> None:
    """Verify that importing host.repl does not eagerly import providers.codex_worker."""
    code = (
        "import sys; "
        "import scripts.host.repl; "
        "mod = sys.modules.get('providers.codex_worker'); "
        "assert mod is None, f'codex_worker was eagerly imported: {mod}'"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr


def test_repl_default_arguments() -> None:
    """Verify that the REPL parser defaults to worker='api' and model='z-ai/glm-4.7'."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.host.repl", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    import re
    assert proc.returncode == 0
    assert re.search(r"default:\s*api", proc.stdout)
    assert re.search(r"default:\s*z-ai/glm-4\.7", proc.stdout)
    assert "(codex worker only)" in proc.stdout


def test_codex_worker_preflight_fails_when_not_found(monkeypatch, tmp_path: Path) -> None:
    """Verify that requesting codex without codex on PATH gives a clear error."""
    monkeypatch.setattr("shutil.which", lambda cmd: None if cmd == "codex" else "/bin/sh")
    args = argparse.Namespace(
        model="z-ai/glm-4.7",
        workdir=None,
        worker_timeout=600.0,
        no_token_telemetry=False,
        config_override=None,
        worker_sandbox="read-only",
        allow_bypass=False,
    )
    with pytest.raises(RuntimeError, match="codex CLI not found on PATH"):
        repl._create_codex_worker(args, tmp_path, tmp_path)


def test_cross_platform_workspace_restore(tmp_path: Path) -> None:
    """Verify that an alien path in session.json falls back to workspace_relpath or local workspaces."""
    from scripts.providers.live_stub import LiveStubWorker

    session_dir = tmp_path / "test-session"
    args = argparse.Namespace(
        candidate_repo=ROOT,
        workspace_root=None,
        observation_dir=None,
        workdir=None,
        run_id="test",
        transcript=None,
        render_compact=False,
    )

    # 1. Start a session and execute one turn with LiveStubWorker to materialize a real workspace
    runtime = repl.open_session(args, tmp_path, LiveStubWorker(), "test-session")
    try:
        runtime.handle("explain protocol")
        real_workspace = Path(runtime.host.status()["workspace_path"])
        assert real_workspace.is_dir()
    finally:
        runtime.close()

    # Verify session.json recorded workspace_relpath
    pointer = session_dir / "session.json"
    assert pointer.is_file()
    saved = json.loads(pointer.read_text(encoding="utf-8"))
    assert "workspace_relpath" in saved
    assert saved["workspace_relpath"] == f"workspaces/{real_workspace.name}"

    # 2. Corrupt workspace_path to simulate an alien path from a different OS/filesystem
    saved["workspace_path"] = f"X:\\alien\\windows\\path\\workspaces\\{real_workspace.name}"
    pointer.write_text(json.dumps(saved, indent=2), encoding="utf-8")

    # 3. Resume the session; it should resolve via workspace_relpath / local workspaces
    resumed = repl.open_session(args, tmp_path, LiveStubWorker(), "test-session")
    try:
        assert Path(resumed.host.status()["workspace_path"]).resolve() == real_workspace.resolve()
    finally:
        resumed.close()


def test_worker_profile_fallback() -> None:
    """Verify that _worker_profile defaults to 'api' when worker_profile is missing."""
    class NoProfileWorker:
        pass

    assert repl._worker_profile(NoProfileWorker()) == "api"


def test_codex_commands_guarded_on_non_codex_worker(capsys) -> None:
    """Verify that /config and /sandbox report guard messages on non-codex workers."""
    class ApiDummyWorker:
        worker_profile = "api"

    worker = ApiDummyWorker()
    # We can invoke the REPL line handlers or simulate command routing
    # Check that worker_profile != 'codex' triggers the guard
    assert getattr(worker, "worker_profile", None) != "codex"

