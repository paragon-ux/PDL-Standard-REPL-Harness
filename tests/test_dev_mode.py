"""Tests for Agentic Dev Mode in PDLt REPL (/dev command suite and telemetry)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdl_taskmaster.host.repl import _handle_dev_command


class FakeWorker:
    def __init__(self):
        self.worker_profile = "api"
        self.model = "test/model-default"
        self.timeout = 60.0
        self.max_tokens = 4096
        self.provider_pinning = {
            "order": ["Groq", "Baseten", "Amazon Bedrock"],
            "allow_fallbacks": True,
        }
        self.model_by_operation = {}
        self.reasoning_by_operation = {}
        self.api_key_env = "OPENROUTER_API_KEY"


class FakeRuntime:
    def __init__(self, tmp_path: Path):
        self.session_id = "test-session-1"
        self.session_dir = tmp_path / "test-session-1"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.host = MagicMock()
        self.host.engine = None
        self.host.candidate_repo = Path.cwd()
        self.host.status.return_value = {
            "workspace_path": str(tmp_path / "ws"),
            "controller_state": {"stage": "PROMPT_REVIEW", "instance_id": "inst-1"},
        }


@pytest.fixture
def dev_env(tmp_path: Path):
    worker = FakeWorker()
    runtime = FakeRuntime(tmp_path)
    return runtime, worker, tmp_path


def test_dev_help(dev_env, capsys):
    runtime, worker, base = dev_env
    handled, mode = _handle_dev_command("/dev", False, runtime, worker, base)
    assert handled is True
    assert mode is False
    out = capsys.readouterr().out
    assert "Dev Mode (Agentic Diagnostic & Control Plane)" in out
    assert "/dev set" in out


def test_dev_toggle(dev_env, capsys):
    runtime, worker, base = dev_env
    handled, mode = _handle_dev_command("/dev on", False, runtime, worker, base)
    assert handled is True
    assert mode is True
    assert "[dev] mode: on" in capsys.readouterr().out

    handled, mode = _handle_dev_command("/dev off", True, runtime, worker, base)
    assert handled is True
    assert mode is False
    assert "[dev] mode: off" in capsys.readouterr().out


def test_dev_status(dev_env, capsys):
    runtime, worker, base = dev_env
    handled, _ = _handle_dev_command("/dev status", True, runtime, worker, base)
    assert handled is True
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["dev_mode"] is True
    assert data["session_id"] == "test-session-1"
    assert data["controller_stage"] == "PROMPT_REVIEW"
    assert data["provider_pinning"]["order"] == ["Groq", "Baseten", "Amazon Bedrock"]


def test_dev_diagnose(dev_env, capsys):
    runtime, worker, base = dev_env
    handled, _ = _handle_dev_command("/dev diagnose", False, runtime, worker, base)
    assert handled is True
    out = capsys.readouterr().out
    assert "[dev:diagnose] Running PDLt system self-test..." in out
    assert "Standards Store: PASS" in out
    assert "Provider Pinning: PASS" in out


def test_dev_mutations_provider_and_fallbacks(dev_env, capsys):
    runtime, worker, base = dev_env
    _handle_dev_command("/dev set provider baseten,groq,amazon-bedrock", False, runtime, worker, base)
    assert worker.provider_pinning["order"] == ["Baseten", "Groq", "Amazon Bedrock"]

    _handle_dev_command("/dev set fallbacks false", False, runtime, worker, base)
    assert worker.provider_pinning["allow_fallbacks"] is False

    _handle_dev_command("/dev set fallbacks true", False, runtime, worker, base)
    assert worker.provider_pinning["allow_fallbacks"] is True


def test_dev_mutations_model_and_reasoning(dev_env, capsys):
    runtime, worker, base = dev_env
    _handle_dev_command("/dev set model EXECUTE deepseek/deepseek-r1", False, runtime, worker, base)
    assert worker.model_by_operation["EXECUTE"] == "deepseek/deepseek-r1"

    _handle_dev_command("/dev set reasoning DRAFT_PLAN high", False, runtime, worker, base)
    assert worker.reasoning_by_operation["DRAFT_PLAN"] == "high"


def test_dev_mutations_timeout_and_tokens(dev_env, capsys):
    runtime, worker, base = dev_env
    _handle_dev_command("/dev set timeout 45.5", False, runtime, worker, base)
    assert worker.timeout == 45.5

    _handle_dev_command("/dev set max_tokens 2048", False, runtime, worker, base)
    assert worker.max_tokens == 2048


def test_dev_get(dev_env, capsys):
    runtime, worker, base = dev_env
    _handle_dev_command("/dev get timeout", False, runtime, worker, base)
    assert "60" in capsys.readouterr().out

    _handle_dev_command("/dev get", False, runtime, worker, base)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["timeout"] == 60.0
