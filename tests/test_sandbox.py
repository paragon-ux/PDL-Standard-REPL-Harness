from __future__ import annotations

import os
import sys
import tempfile
import pytest
from pathlib import Path

from pdl_taskmaster.verification.sandbox import ExecutionSandbox, SandboxResult


def test_sandbox_success_execution():
    sandbox = ExecutionSandbox(timeout_seconds=5.0)
    result = sandbox.run_code("print('HELLO FROM SANDBOX')")
    assert result.success
    assert result.exit_code == 0
    assert "HELLO FROM SANDBOX" in result.stdout
    assert not result.timed_out
    assert not result.oom_killed
    assert result.duration_ms > 0.0


def test_sandbox_timeout_termination():
    sandbox = ExecutionSandbox(timeout_seconds=0.5)
    # An infinite loop must be terminated by the sandbox
    result = sandbox.run_code("import time\nwhile True:\n    time.sleep(0.05)")
    assert not result.success
    assert result.timed_out
    assert result.exit_code in (124, 1, -1)


def test_sandbox_memory_limit_oom():
    # 50 MB limit, attempting 120 MB allocation
    sandbox = ExecutionSandbox(timeout_seconds=5.0, memory_limit_bytes=50 * 1024 * 1024)
    result = sandbox.run_code("x = bytearray(120 * 1024 * 1024)\nprint(len(x))")
    assert not result.success
    assert result.oom_killed
    assert result.exit_code != 0


def test_sandbox_network_blocking():
    # Default sandbox forbids network access
    sandbox = ExecutionSandbox(allow_network=False)
    code = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
"""
    result = sandbox.run_code(code)
    assert not result.success
    assert result.exit_code != 0
    assert "Network access is strictly disabled" in result.stderr or "PermissionError" in result.stderr


def test_sandbox_scratchpad_cleanup():
    sandbox = ExecutionSandbox()
    test_marker = "sandbox_scratchpad_test_marker.txt"
    code = f"""
with open({test_marker!r}, "w") as f:
    f.write("temporary data")
print("WROTE_FILE")
"""
    result = sandbox.run_code(code)
    assert result.success
    assert "WROTE_FILE" in result.stdout
    # Verify file is not in current working dir
    assert not Path(test_marker).exists()


def test_sandbox_low_overhead():
    # Verify execution overhead is minimal
    sandbox = ExecutionSandbox()
    result = sandbox.run_code("x = 1 + 1\nprint(x)")
    assert result.success
    assert "2" in result.stdout.strip()
    # Python startup + Windows Job Object assignment should complete promptly
    assert result.duration_ms < 2500.0
